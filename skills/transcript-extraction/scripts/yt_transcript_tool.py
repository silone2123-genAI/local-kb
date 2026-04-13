import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
from typing import Optional, List, Dict, Any

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig


VIDEO_RETRY_COUNT = 6
BASE_BACKOFF_SECONDS = 6
MAX_BACKOFF_SECONDS = 60

BETWEEN_VIDEO_SLEEP_SECONDS = 60


class OpenClawTranscriptTool:
    def __init__(
        self,
        proxy_username: str,
        proxy_password: str,
        rotate_after_uses: int = 8,
        filter_ip_locations: Optional[List[str]] = None,
        debug: bool = False,
    ):
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.rotate_after_uses = rotate_after_uses
        self.filter_ip_locations = filter_ip_locations or []
        self.debug = debug

        self._api: Optional[YouTubeTranscriptApi] = None
        self._api_use_count = 0
        self._build_api()

    def _build_api(self):
        proxy_config = WebshareProxyConfig(
            proxy_username=self.proxy_username,
            proxy_password=self.proxy_password,
            filter_ip_locations=self.filter_ip_locations or None,
        )
        self._api = YouTubeTranscriptApi(proxy_config=proxy_config)
        self._api_use_count = 0

        if self.debug:
            print("[DEBUG] Rebuilt YouTubeTranscriptApi with WebshareProxyConfig")

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
            ]
            for p in patterns:
                m = re.search(p, url_or_id)
                if m:
                    return m.group(1)
            raise ValueError("Could not parse YouTube video ID")
        return url_or_id

    def fetch_json(
        self,
        url_or_id: str,
        languages: Optional[List[str]] = None,
        preserve_formatting: bool = False,
    ) -> Dict[str, Any]:
        video_id = self.extract_video_id(url_or_id)
        last_error = None

        for attempt in range(1, VIDEO_RETRY_COUNT + 1):
            try:
                self._maybe_rotate()

                if self.debug:
                    print(
                        f"[DEBUG] attempt={attempt} video_id={video_id} "
                        f"api_use_count={self._api_use_count}"
                    )

                transcript = self._api.fetch(
                    video_id,
                    languages=languages or ["en"],
                    preserve_formatting=preserve_formatting,
                )
                raw = transcript.to_raw_data()
                full_text = "\n".join(x["text"] for x in raw)

                self._api_use_count += 1

                return {
                    "video_id": video_id,
                    "language": transcript.language_code,
                    "segments": raw,
                    "text": full_text,
                }

            except Exception as e:
                last_error = e
                message = str(e).lower()

                if self.debug:
                    print(f"[DEBUG] fetch failed: {e}")

                if "429" in message or "too many requests" in message:
                    self.rotate_proxy_session()
                    backoff = min(
                        MAX_BACKOFF_SECONDS,
                        BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)),
                    )
                    sleep_seconds = backoff + random.uniform(2, 6)
                    if self.debug:
                        print(f"[DEBUG] 429 detected, sleeping {sleep_seconds:.1f}s before retry")
                    time.sleep(sleep_seconds)
                    continue

                if any(x in message for x in ["403", "proxy", "timed out", "connection", "reset by peer"]):
                    self.rotate_proxy_session()
                    sleep_seconds = random.uniform(5, 12)
                    if self.debug:
                        print(f"[DEBUG] proxy/network issue, sleeping {sleep_seconds:.1f}s before retry")
                    time.sleep(sleep_seconds)
                    continue

                time.sleep(random.uniform(2, 5))

        raise RuntimeError(f"Failed to fetch transcript after retries: {last_error}")

    def fetch_text(
        self,
        url_or_id: str,
        languages: Optional[List[str]] = None,
        preserve_formatting: bool = False,
    ) -> str:
        return self.fetch_json(
            url_or_id=url_or_id,
            languages=languages,
            preserve_formatting=preserve_formatting,
        )["text"]


def is_video_url(url: str) -> bool:
    return (
        "watch?v=" in url
        or "youtu.be/" in url
        or "/shorts/" in url
        or "/embed/" in url
        or re.fullmatch(r"[A-Za-z0-9_-]{11}", url or "") is not None
    )


def ensure_output_dir(path: str):
    os.makedirs(path, exist_ok=True)


def save_transcript_markdown(
    output_dir: str,
    title: str,
    video_id: str,
    video_url: str,
    language: str,
    text: str,
) -> str:
    filename = f"{video_id}.md"
    file_path = os.path.join(output_dir, filename)

    content = f"""# {title}

- Video ID: `{video_id}`
- URL: {video_url}
- Language: `{language}`

## Transcript

{text}
"""

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


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


def shlex_quote(s: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=@-]+", s):
        return s
    return "'" + s.replace("'", "'\"'\"'") + "'"


def build_clean_env_for_yt_dlp(disable_env_proxy: bool = True) -> Dict[str, str]:
    env = os.environ.copy()

    if disable_env_proxy:
        for key in [
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
            "http_proxy", "https_proxy", "all_proxy",
        ]:
            env.pop(key, None)

    return env


def build_yt_dlp_proxy_args(proxy_url: Optional[str], disable_proxy: bool) -> List[str]:
    if disable_proxy:
        return ["--proxy", ""]

    if proxy_url:
        return ["--proxy", proxy_url]

    return []


def run_yt_dlp_json_command(
    cmd: List[str],
    debug: bool = False,
    disable_env_proxy: bool = True,
) -> Dict[str, Any]:
    if debug:
        print("[DEBUG] Running command:")
        print("[DEBUG] " + " ".join(shlex_quote(x) for x in cmd))

    env = build_clean_env_for_yt_dlp(disable_env_proxy=disable_env_proxy)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
    )

    if debug:
        if proc.stdout.strip():
            print("[DEBUG] yt-dlp stdout:")
            print(proc.stdout[:4000])
        if proc.stderr.strip():
            print("[DEBUG] yt-dlp stderr:")
            print(proc.stderr[:4000])

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()
        detail = stderr or stdout or f"yt-dlp exited with code {proc.returncode}"
        raise RuntimeError(f"yt-dlp failed: {detail}")

    if not proc.stdout.strip():
        raise RuntimeError("yt-dlp returned success but no JSON output")

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"yt-dlp returned non-JSON output: {e}; output starts with: {proc.stdout[:500]!r}"
        ) from e


def list_video_entries_by_date(
    source_url: str,
    dateafter: Optional[str] = None,
    datebefore: Optional[str] = None,
    debug: bool = False,
    yt_dlp_proxy_url: Optional[str] = None,
    disable_yt_dlp_proxy: bool = True,
) -> List[Dict[str, str]]:
    source_url = normalize_youtube_collection_url(source_url)

    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
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

    results = []
    for item in entries:
        video_id = item.get("id")
        title = item.get("title") or video_id or "untitled"
        url = item.get("url")

        if video_id:
            if url and url.startswith("http"):
                video_url = url
            else:
                video_url = f"https://www.youtube.com/watch?v={video_id}"

            results.append({
                "id": video_id,
                "title": title,
                "url": video_url,
            })

    return results


def get_single_video_title(
    url: str,
    debug: bool = False,
    yt_dlp_proxy_url: Optional[str] = None,
    disable_yt_dlp_proxy: bool = True,
) -> str:
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--print",
        "%(title)s",
        *build_yt_dlp_proxy_args(
            proxy_url=yt_dlp_proxy_url,
            disable_proxy=disable_yt_dlp_proxy,
        ),
        url,
    ]

    if debug:
        print("[DEBUG] Running command:")
        print("[DEBUG] " + " ".join(shlex_quote(x) for x in cmd))

    env = build_clean_env_for_yt_dlp(disable_env_proxy=disable_yt_dlp_proxy)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
    )

    if debug and proc.stderr.strip():
        print("[DEBUG] yt-dlp stderr:")
        print(proc.stderr[:4000])

    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()

    return "untitled"


def get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="YouTube video URL / video id / channel URL / playlist URL")
    parser.add_argument("--dateafter", help="Only process videos uploaded after YYYYMMDD")
    parser.add_argument("--datebefore", help="Only process videos uploaded on or before YYYYMMDD")
    parser.add_argument("--languages", nargs="+", default=["en"])
    parser.add_argument("--output-dir", default="transcripts_md")
    parser.add_argument("--filter-ip-locations", nargs="*", default=[])
    parser.add_argument("--debug", action="store_true")

    parser.add_argument(
        "--total-limit", type=int, default=None, help="Maximum number of videos to process."
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

    args = parser.parse_args()

    ensure_output_dir(args.output_dir)

    proxy_username = get_required_env("WEBSHARE_PROXY_USERNAME")
    proxy_password = get_required_env("WEBSHARE_PROXY_PASSWORD")

    tool = OpenClawTranscriptTool(
        proxy_username=proxy_username,
        proxy_password=proxy_password,
        rotate_after_uses=8,
        filter_ip_locations=args.filter_ip_locations,
        debug=args.debug,
    )

    disable_yt_dlp_proxy = not args.use_yt_dlp_proxy

    if is_video_url(args.input):
        result = tool.fetch_json(args.input, languages=args.languages)
        video_id = result["video_id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        title = get_single_video_title(
            video_url,
            debug=args.debug,
            yt_dlp_proxy_url=args.yt_dlp_proxy_url,
            disable_yt_dlp_proxy=disable_yt_dlp_proxy,
        )
        file_path = save_transcript_markdown(
            output_dir=args.output_dir,
            title=title,
            video_id=video_id,
            video_url=video_url,
            language=result["language"],
            text=result["text"],
        )
        print(f"Saved: {file_path}")
        return

    if not args.dateafter and not args.datebefore:
        raise RuntimeError(
            "For channel or playlist URLs, provide at least one of "
            "--dateafter YYYYMMDD or --datebefore YYYYMMDD"
        )

    video_entries = list_video_entries_by_date(
        args.input,
        dateafter=args.dateafter,
        datebefore=args.datebefore,
        debug=args.debug,
        yt_dlp_proxy_url=args.yt_dlp_proxy_url,
        disable_yt_dlp_proxy=disable_yt_dlp_proxy,
    )

    if not video_entries:
        print("No videos found for the given date filter.")
        return

    for idx, item in enumerate(video_entries, 1):
        if args.total_limit is not None and idx > args.total_limit:
            print(f"Reached total limit of {args.total_limit} videos. Stopping.")
            break

        video_url = item["url"]
        title = item["title"]

        try:
            result = tool.fetch_json(video_url, languages=args.languages)
            file_path = save_transcript_markdown(
                output_dir=args.output_dir,
                title=title,
                video_id=result["video_id"],
                video_url=video_url,
                language=result["language"],
                text=result["text"],
            )
            print(f"===== VIDEO {idx}: SAVED =====")
            print(file_path)
            print()
        except Exception as e:
            print(f"===== VIDEO {idx}: FAILED =====")
            print(f"{video_url} -> {e}")
            print()

        time.sleep(BETWEEN_VIDEO_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
