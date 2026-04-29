import argparse
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig
    YOUTUBE_TRANSCRIPT_IMPORT_ERROR = None
except Exception as import_error:  # pragma: no cover - depends on installed youtube-transcript-api version
    YouTubeTranscriptApi = None
    GenericProxyConfig = None
    WebshareProxyConfig = None
    YOUTUBE_TRANSCRIPT_IMPORT_ERROR = import_error


VIDEO_RETRY_COUNT = 6
BASE_BACKOFF_SECONDS = 6
MAX_BACKOFF_SECONDS = 60
DEFAULT_SOURCE_LIMIT = 16
MAX_SOURCE_LIMIT = 16
DEFAULT_BETWEEN_VIDEO_SLEEP_SECONDS = 5


class OpenClawTranscriptTool:
    def __init__(
        self,
        proxy_username: Optional[str] = None,
        proxy_password: Optional[str] = None,
        rotate_after_uses: int = 8,
        filter_ip_locations: Optional[List[str]] = None,
        transcript_http_proxy: Optional[str] = None,
        transcript_https_proxy: Optional[str] = None,
        debug: bool = False,
    ):
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.rotate_after_uses = rotate_after_uses
        self.filter_ip_locations = filter_ip_locations or []
        self.transcript_http_proxy = transcript_http_proxy
        self.transcript_https_proxy = transcript_https_proxy
        self.debug = debug

        self._api: Optional[Any] = None
        self._api_use_count = 0
        self._build_api()

    def _build_api(self):
        if YouTubeTranscriptApi is None:
            raise RuntimeError(
                "Could not import youtube-transcript-api. Install or repair it with "
                "`python3 -m pip install -U youtube-transcript-api`. "
                f"Import error: {YOUTUBE_TRANSCRIPT_IMPORT_ERROR}"
            )

        kwargs: Dict[str, Any] = {}

        if self.proxy_username and self.proxy_password:
            if WebshareProxyConfig is None:
                raise RuntimeError(
                    "This youtube-transcript-api install does not expose WebshareProxyConfig. "
                    "Upgrade youtube-transcript-api or use no transcript proxy."
                )

            kwargs["proxy_config"] = WebshareProxyConfig(
                proxy_username=self.proxy_username,
                proxy_password=self.proxy_password,
                filter_ip_locations=self.filter_ip_locations or None,
            )
        elif self.transcript_http_proxy or self.transcript_https_proxy:
            if GenericProxyConfig is None:
                raise RuntimeError(
                    "This youtube-transcript-api install does not expose GenericProxyConfig. "
                    "Upgrade youtube-transcript-api or use Webshare env vars."
                )

            kwargs["proxy_config"] = GenericProxyConfig(
                http_url=self.transcript_http_proxy,
                https_url=self.transcript_https_proxy,
            )

        self._api = YouTubeTranscriptApi(**kwargs)
        self._api_use_count = 0

        if self.debug:
            proxy_mode = "none"
            if self.proxy_username and self.proxy_password:
                proxy_mode = "webshare"
            elif self.transcript_http_proxy or self.transcript_https_proxy:
                proxy_mode = "generic"
            print(f"[DEBUG] Rebuilt YouTubeTranscriptApi proxy_mode={proxy_mode}")

    def rotate_proxy_session(self):
        self._build_api()

    def _maybe_rotate(self):
        if self._api is None or self._api_use_count >= self.rotate_after_uses:
            self.rotate_proxy_session()

    def extract_video_id(self, url_or_id: str) -> str:
        if "youtube.com" in url_or_id or "youtu.be" in url_or_id:
            patterns = [
                r"[?&]v=([^&]+)",
                r"youtu\.be/([^?&/]+)",
                r"shorts/([^?&/]+)",
                r"embed/([^?&/]+)",
                r"/live/([^?&/]+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, url_or_id)
                if match:
                    return match.group(1)
            raise ValueError("Could not parse YouTube video ID")
        return url_or_id

    def _fetch_transcript(
        self,
        video_id: str,
        languages: List[str],
        preserve_formatting: bool,
    ) -> Tuple[List[Dict[str, Any]], str]:
        if self._api is not None and hasattr(self._api, "fetch"):
            transcript = self._api.fetch(
                video_id,
                languages=languages,
                preserve_formatting=preserve_formatting,
            )
            return transcript.to_raw_data(), getattr(transcript, "language_code", languages[0])

        # Compatibility path for older youtube-transcript-api releases.
        raw = YouTubeTranscriptApi.get_transcript(  # type: ignore[attr-defined]
            video_id,
            languages=languages,
            preserve_formatting=preserve_formatting,
        )
        return raw, languages[0]

    def fetch_json(
        self,
        url_or_id: str,
        languages: Optional[List[str]] = None,
        preserve_formatting: bool = False,
    ) -> Dict[str, Any]:
        video_id = self.extract_video_id(url_or_id)
        language_preferences = languages or ["en"]
        last_error = None

        for attempt in range(1, VIDEO_RETRY_COUNT + 1):
            try:
                self._maybe_rotate()

                if self.debug:
                    print(
                        f"[DEBUG] attempt={attempt} video_id={video_id} "
                        f"api_use_count={self._api_use_count}"
                    )

                raw, language_code = self._fetch_transcript(
                    video_id=video_id,
                    languages=language_preferences,
                    preserve_formatting=preserve_formatting,
                )
                full_text = "\n".join(item.get("text", "") for item in raw).strip()

                self._api_use_count += 1

                return {
                    "video_id": video_id,
                    "language": language_code,
                    "segments": raw,
                    "text": full_text,
                }

            except Exception as error:
                last_error = error
                message = str(error).lower()

                if self.debug:
                    print(f"[DEBUG] fetch failed: {error}")

                if any(
                    token in message
                    for token in ["failed to resolve", "name resolution", "nodename nor servname"]
                ):
                    break

                if "429" in message or "too many requests" in message:
                    self.rotate_proxy_session()
                    backoff = min(
                        MAX_BACKOFF_SECONDS,
                        BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)),
                    )
                    sleep_seconds = backoff + random.uniform(2, 6)
                    if self.debug:
                        print(f"[DEBUG] rate limit detected; sleeping {sleep_seconds:.1f}s")
                    time.sleep(sleep_seconds)
                    continue

                if any(
                    token in message
                    for token in ["403", "proxy", "timed out", "connection", "reset by peer"]
                ):
                    self.rotate_proxy_session()
                    sleep_seconds = random.uniform(5, 12)
                    if self.debug:
                        print(f"[DEBUG] proxy/network issue; sleeping {sleep_seconds:.1f}s")
                    time.sleep(sleep_seconds)
                    continue

                time.sleep(random.uniform(2, 5))

        raise RuntimeError(f"Failed to fetch transcript after retries: {last_error}")


def is_video_url(url: str) -> bool:
    return (
        "watch?v=" in url
        or "youtu.be/" in url
        or "/shorts/" in url
        or "/embed/" in url
        or "/live/" in url
        or re.fullmatch(r"[A-Za-z0-9_-]{11}", url or "") is not None
    )


def ensure_output_dir(path: str):
    os.makedirs(path, exist_ok=True)


def normalize_youtube_collection_url(url: str) -> str:
    url = url.strip()

    if "youtube.com" not in url:
        return url

    parsed = re.sub(r"#.*$", "", url).rstrip("/")

    if any(
        parsed.endswith(suffix)
        for suffix in (
            "/videos",
            "/shorts",
            "/streams",
            "/playlists",
            "/featured",
            "/releases",
            "/podcasts",
        )
    ):
        return parsed

    if re.search(r"youtube\.com/@[^/]+$", parsed):
        return parsed + "/videos"

    if re.search(r"youtube\.com/channel/[^/]+$", parsed):
        return parsed + "/videos"

    if re.search(r"youtube\.com/c/[^/]+$", parsed):
        return parsed + "/videos"

    if re.search(r"youtube\.com/user/[^/]+$", parsed):
        return parsed + "/videos"

    return parsed


def shlex_quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=@-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def build_clean_env_for_yt_dlp(disable_env_proxy: bool = True) -> Dict[str, str]:
    env = os.environ.copy()

    if disable_env_proxy:
        for key in [
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ]:
            env.pop(key, None)

    return env


def build_yt_dlp_proxy_args(proxy_url: Optional[str], disable_proxy: bool) -> List[str]:
    if disable_proxy:
        return ["--proxy", ""]

    if proxy_url:
        return ["--proxy", proxy_url]

    return []


def build_yt_dlp_base_command() -> List[str]:
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]

    executable = shutil.which("yt-dlp")
    if executable:
        return [executable]

    return [sys.executable, "-m", "yt_dlp"]


def run_yt_dlp_json_command(
    cmd: List[str],
    debug: bool = False,
    disable_env_proxy: bool = True,
) -> Dict[str, Any]:
    if debug:
        print("[DEBUG] Running command:")
        print("[DEBUG] " + " ".join(shlex_quote(item) for item in cmd))

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=build_clean_env_for_yt_dlp(disable_env_proxy=disable_env_proxy),
    )

    if debug:
        if proc.stdout.strip():
            print("[DEBUG] yt-dlp stdout:")
            print(proc.stdout[:4000])
        if proc.stderr.strip():
            print("[DEBUG] yt-dlp stderr:")
            print(proc.stderr[:4000])

    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"yt-dlp exited with code {proc.returncode}"
        raise RuntimeError(f"yt-dlp failed: {detail}")

    if not proc.stdout.strip():
        raise RuntimeError("yt-dlp returned success but no JSON output")

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"yt-dlp returned non-JSON output: {error}; output starts with: {proc.stdout[:500]!r}"
        ) from error


def run_yt_dlp_lines_command(
    cmd: List[str],
    debug: bool = False,
    disable_env_proxy: bool = True,
) -> List[str]:
    if debug:
        print("[DEBUG] Running command:")
        print("[DEBUG] " + " ".join(shlex_quote(item) for item in cmd))

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=build_clean_env_for_yt_dlp(disable_env_proxy=disable_env_proxy),
    )

    if debug and proc.stderr.strip():
        print("[DEBUG] yt-dlp stderr:")
        print(proc.stderr[:4000])

    if proc.returncode != 0:
        return []

    return [line.strip() for line in proc.stdout.splitlines()]


def valid_yyyymmdd(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    if not re.fullmatch(r"\d{8}", value):
        raise argparse.ArgumentTypeError("Date must be YYYYMMDD")

    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as error:
        raise argparse.ArgumentTypeError("Date must be a real calendar date") from error

    return value


def date_in_window(
    upload_date: Optional[str],
    dateafter: Optional[str],
    datebefore: Optional[str],
) -> bool:
    if not upload_date or not re.fullmatch(r"\d{8}", upload_date):
        return True

    if dateafter and upload_date <= dateafter:
        return False

    if datebefore and upload_date > datebefore:
        return False

    return True


def clamp_source_limit(value: Optional[int]) -> int:
    if value is None:
        return DEFAULT_SOURCE_LIMIT

    if value < 1:
        raise argparse.ArgumentTypeError("Limit must be at least 1")

    return min(value, MAX_SOURCE_LIMIT)


def save_transcript_markdown(
    output_dir: str,
    title: str,
    video_id: str,
    video_url: str,
    language: str,
    text: str,
    upload_date: Optional[str] = None,
) -> str:
    filename = f"{video_id}.md"
    file_path = os.path.join(output_dir, filename)
    upload_line = f"- Upload date: `{upload_date}`\n" if upload_date else ""

    content = f"""# {title}

- Video ID: `{video_id}`
- URL: {video_url}
{upload_line}- Language: `{language}`

## Transcript

{text}
"""

    with open(file_path, "w", encoding="utf-8") as file:
        file.write(content)

    return file_path


def save_run_summary(output_dir: str, summary: Dict[str, Any]) -> str:
    file_path = os.path.join(output_dir, "run_summary.json")
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2, ensure_ascii=False)
        file.write("\n")
    return file_path


def list_video_entries_by_date(
    source_url: str,
    dateafter: Optional[str] = None,
    datebefore: Optional[str] = None,
    debug: bool = False,
    yt_dlp_proxy_url: Optional[str] = None,
    disable_yt_dlp_proxy: bool = True,
    source_limit: int = DEFAULT_SOURCE_LIMIT,
) -> List[Dict[str, Optional[str]]]:
    source_url = normalize_youtube_collection_url(source_url)

    cmd = [
        *build_yt_dlp_base_command(),
        "--flat-playlist",
        "--dump-single-json",
        *build_yt_dlp_proxy_args(
            proxy_url=yt_dlp_proxy_url,
            disable_proxy=disable_yt_dlp_proxy,
        ),
    ]

    if dateafter:
        cmd.extend(["--dateafter", dateafter])

    if datebefore:
        cmd.extend(["--datebefore", datebefore])

    cmd.append(source_url)

    data = run_yt_dlp_json_command(
        cmd,
        debug=debug,
        disable_env_proxy=disable_yt_dlp_proxy,
    )
    entries = data.get("entries", []) or []

    results: List[Dict[str, Optional[str]]] = []
    seen_ids = set()
    for item in entries:
        video_id = item.get("id")
        if not video_id or video_id in seen_ids:
            continue

        seen_ids.add(video_id)
        url = item.get("url")
        video_url = url if url and url.startswith("http") else f"https://www.youtube.com/watch?v={video_id}"

        results.append(
            {
                "id": video_id,
                "title": item.get("title") or video_id,
                "url": video_url,
                "upload_date": item.get("upload_date"),
            }
        )

        if len(results) >= source_limit:
            break

    return results


def get_single_video_metadata(
    url: str,
    debug: bool = False,
    yt_dlp_proxy_url: Optional[str] = None,
    disable_yt_dlp_proxy: bool = True,
) -> Dict[str, Optional[str]]:
    lines = run_yt_dlp_lines_command(
        [
            *build_yt_dlp_base_command(),
            "--print",
            "%(title)s",
            "--print",
            "%(upload_date)s",
            *build_yt_dlp_proxy_args(
                proxy_url=yt_dlp_proxy_url,
                disable_proxy=disable_yt_dlp_proxy,
            ),
            url,
        ],
        debug=debug,
        disable_env_proxy=disable_yt_dlp_proxy,
    )

    title = lines[0] if len(lines) >= 1 and lines[0] != "NA" else "untitled"
    upload_date = lines[1] if len(lines) >= 2 and re.fullmatch(r"\d{8}", lines[1]) else None
    return {"title": title, "upload_date": upload_date}


def build_date_filters(args: argparse.Namespace) -> Tuple[Optional[str], Optional[str]]:
    dateafter = args.dateafter
    datebefore = args.datebefore

    if args.year:
        year_after = f"{args.year}0101"
        year_before = f"{args.year}1231"
        dateafter = max(dateafter, year_after) if dateafter else year_after
        datebefore = min(datebefore, year_before) if datebefore else year_before

    return dateafter, datebefore


def build_summary(args: argparse.Namespace, dateafter: Optional[str], datebefore: Optional[str]) -> Dict[str, Any]:
    return {
        "input": args.input,
        "output_dir": args.output_dir,
        "dateafter": dateafter,
        "datebefore": datebefore,
        "source_limit": args.total_limit,
        "languages": args.languages,
        "saved": [],
        "failed": [],
        "skipped": [],
    }


def add_transcript_proxy_args(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--use-transcript-proxy",
        action="store_true",
        help="Use transcript proxy settings. If Webshare env vars are set, they are preferred.",
    )
    parser.add_argument("--transcript-http-proxy", default=None)
    parser.add_argument("--transcript-https-proxy", default=None)


def main():
    parser = argparse.ArgumentParser(
        description="Extract YouTube transcripts from a video, channel, or playlist URL."
    )
    parser.add_argument("input", help="YouTube video URL / video id / channel URL / playlist URL")
    parser.add_argument("--dateafter", type=valid_yyyymmdd, help="Only process videos uploaded after YYYYMMDD")
    parser.add_argument("--datebefore", type=valid_yyyymmdd, help="Only process videos uploaded on or before YYYYMMDD")
    parser.add_argument("--year", type=int, help="Only process videos from a calendar year")
    parser.add_argument("--languages", nargs="+", default=["en"])
    parser.add_argument("--output-dir", default="transcripts_md")
    parser.add_argument("--filter-ip-locations", nargs="*", default=[])
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--total-limit",
        "--source-limit",
        dest="total_limit",
        type=clamp_source_limit,
        default=DEFAULT_SOURCE_LIMIT,
        help=f"Maximum source videos to process. Defaults to {DEFAULT_SOURCE_LIMIT}; hard capped at {MAX_SOURCE_LIMIT}.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=DEFAULT_BETWEEN_VIDEO_SLEEP_SECONDS,
        help="Seconds to sleep between transcript fetches for channel/playlist runs.",
    )
    parser.add_argument(
        "--yt-dlp-proxy-url",
        default=None,
        help="Explicit proxy URL for yt-dlp, e.g. http://user:pass@host:port or socks5h://user:pass@host:port",
    )
    parser.add_argument(
        "--use-yt-dlp-proxy",
        action="store_true",
        help="Allow yt-dlp to use the explicit --yt-dlp-proxy-url",
    )
    add_transcript_proxy_args(parser)

    args = parser.parse_args()
    dateafter, datebefore = build_date_filters(args)
    ensure_output_dir(args.output_dir)

    proxy_username = os.environ.get("WEBSHARE_PROXY_USERNAME") if args.use_transcript_proxy else None
    proxy_password = os.environ.get("WEBSHARE_PROXY_PASSWORD") if args.use_transcript_proxy else None

    tool = OpenClawTranscriptTool(
        proxy_username=proxy_username,
        proxy_password=proxy_password,
        rotate_after_uses=8,
        filter_ip_locations=args.filter_ip_locations,
        transcript_http_proxy=args.transcript_http_proxy if args.use_transcript_proxy else None,
        transcript_https_proxy=args.transcript_https_proxy if args.use_transcript_proxy else None,
        debug=args.debug,
    )

    disable_yt_dlp_proxy = not args.use_yt_dlp_proxy
    summary = build_summary(args, dateafter, datebefore)

    if is_video_url(args.input):
        video_id = tool.extract_video_id(args.input)
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        metadata = get_single_video_metadata(
            video_url,
            debug=args.debug,
            yt_dlp_proxy_url=args.yt_dlp_proxy_url,
            disable_yt_dlp_proxy=disable_yt_dlp_proxy,
        )

        if not date_in_window(metadata.get("upload_date"), dateafter, datebefore):
            reason = "single video is outside the requested date window"
            print(f"Skipped: {video_url} ({reason})")
            summary["skipped"].append({"url": video_url, "reason": reason, **metadata})
            save_run_summary(args.output_dir, summary)
            return

        try:
            result = tool.fetch_json(video_url, languages=args.languages)
            file_path = save_transcript_markdown(
                output_dir=args.output_dir,
                title=metadata.get("title") or "untitled",
                video_id=result["video_id"],
                video_url=video_url,
                language=result["language"],
                text=result["text"],
                upload_date=metadata.get("upload_date"),
            )
            summary["saved"].append({"video_id": result["video_id"], "url": video_url, "file": file_path})
            print(f"Saved: {file_path}")
        except Exception as error:
            summary["failed"].append({"url": video_url, "error": str(error)})
            print(f"Failed: {video_url} -> {error}")

        save_run_summary(args.output_dir, summary)
        return

    video_entries = list_video_entries_by_date(
        args.input,
        dateafter=dateafter,
        datebefore=datebefore,
        debug=args.debug,
        yt_dlp_proxy_url=args.yt_dlp_proxy_url,
        disable_yt_dlp_proxy=disable_yt_dlp_proxy,
        source_limit=args.total_limit,
    )

    if not video_entries:
        print("No videos found for the given URL/date filter.")
        save_run_summary(args.output_dir, summary)
        return

    print(f"Found {len(video_entries)} source video(s). Processing up to {args.total_limit}.")
    for idx, item in enumerate(video_entries, 1):
        video_url = item["url"]
        title = item["title"] or item["id"] or "untitled"

        try:
            result = tool.fetch_json(str(video_url), languages=args.languages)
            file_path = save_transcript_markdown(
                output_dir=args.output_dir,
                title=str(title),
                video_id=result["video_id"],
                video_url=str(video_url),
                language=result["language"],
                text=result["text"],
                upload_date=item.get("upload_date"),
            )
            summary["saved"].append({"video_id": result["video_id"], "url": video_url, "file": file_path})
            print(f"===== VIDEO {idx}: SAVED =====")
            print(file_path)
            print()
        except Exception as error:
            summary["failed"].append({"url": video_url, "title": title, "error": str(error)})
            print(f"===== VIDEO {idx}: FAILED =====")
            print(f"{video_url} -> {error}")
            print()

        if idx < len(video_entries) and args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    summary_path = save_run_summary(args.output_dir, summary)
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
