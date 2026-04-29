---
name: transcript-extraction
version: 1.0.0
purpose: Extract YouTube video, playlist, or channel transcripts into one Markdown file per video, with date/year filtering, language preference, and optional proxy support.
---

# transcript-extraction

Use this skill to extract transcripts from a YouTube video, playlist, or creator channel URL and save each transcript into its own Markdown file. Batch runs default to 16 source videos and are hard capped at 16.

This skill is designed for OpenClaw/Claude-style agent workflows where the transcript files become inputs for later summarization, tagging, embeddings, knowledge-base ingestion, or content analysis.

## When to use

Use this skill when the user wants to:
- Pull transcripts from a YouTube channel URL such as `https://www.youtube.com/@Dr.ShadeZahrai`.
- Extract from direct video, playlist, channel, `/videos`, or `/shorts` URLs.
- Filter by date, such as `--dateafter 20260409`.
- Filter by calendar year, such as `--year 2026`.
- Prefer one or more transcript languages.
- Use a proxy for `yt-dlp`, `youtube-transcript-api`, or both.
- Save one Markdown file per video instead of one combined file.

## What this skill does

1. Enumerates video entries from a video URL, playlist URL, or normalized channel `/videos` URL.
2. Applies `yt-dlp` date filtering when provided.
3. Optionally narrows results further to a single year.
4. Retrieves the best available transcript per video using language preferences.
5. Writes each transcript to `[output-dir]/[video_id].md`.
6. Writes a machine-readable run summary to `[output-dir]/run_summary.json`.

## Environment setup

```bash
python3 -m venv openclaw_env
source openclaw_env/bin/activate
python3 -m pip install -U pip
python3 -m pip install youtube-transcript-api
python3 -m pip install -U yt-dlp
```

## Primary command

```bash
python3 [skill-directory]/scripts/yt_transcript_tool.py "https://www.youtube.com/@[youtuber-name]" --dateafter YYYYMMDD
```

## Recommended examples

### Basic channel extraction

```bash
python3 [skill-directory]/scripts/yt_transcript_tool.py "https://www.youtube.com/@Dr.ShadeZahrai"
```

This extracts at most 16 source videos by default.

### Filter to only content published in 2026

```bash
python3 [skill-directory]/scripts/yt_transcript_tool.py "https://www.youtube.com/@Dr.ShadeZahrai" --year 2026
```

### Filter using explicit date window

```bash
python3 [skill-directory]/scripts/yt_transcript_tool.py "https://www.youtube.com/@Dr.ShadeZahrai" --dateafter 20260101 --datebefore 20261231
```

### Prefer multiple languages in priority order

```bash
python3 [skill-directory]/scripts/yt_transcript_tool.py "https://www.youtube.com/@Dr.ShadeZahrai" --languages en zh-Hans zh
```

### Extract a single video

```bash
python3 [skill-directory]/scripts/yt_transcript_tool.py "https://www.youtube.com/watch?v=VIDEO_ID" --languages en
```

### Route yt-dlp through a proxy

```bash
python3 [skill-directory]/scripts/yt_transcript_tool.py "https://www.youtube.com/@Dr.ShadeZahrai" \
  --dateafter 20260409 \
  --use-yt-dlp-proxy \
  --yt-dlp-proxy-url "socks5h://user:pass@host:80"
```

### Route both yt-dlp and transcript fetches through proxies

```bash
python3 [skill-directory]/scripts/yt_transcript_tool.py "https://www.youtube.com/@Dr.ShadeZahrai" \
  --year 2026 \
  --languages en \
  --use-yt-dlp-proxy \
  --yt-dlp-proxy-url "socks5h://user:pass@host:80" \
  --use-transcript-proxy \
  --transcript-http-proxy "http://user:pass@host:8080" \
  --transcript-https-proxy "http://user:pass@host:8080" \
  --debug
```

### Your example

```bash
python3 yt_transcript_tool.py "https://www.youtube.com/@Dr.ShadeZahrai" \
  --dateafter 20260409 \
  --use-yt-dlp-proxy \
  --yt-dlp-proxy-url "socks5h://znmhdedy:bn3fbuctnw4s@p.webshare.io:80" \
  --debug
```

## Output contract

Expected outputs:
- `[output-dir]/[video_id].md` for each transcript successfully saved.
- `[output-dir]/run_summary.json` with saved, failed, skipped, and configuration details.

Each Markdown file includes:
- Video title
- Video ID
- Upload date
- Source URL
- Transcript language metadata
- Transcript body

## Language behavior

Use `--languages` to provide one or more preferred language codes in priority order.

Examples:
- `--languages en`
- `--languages en zh-Hans zh`
- `--languages de en`

The script requests transcripts using the provided language list in priority order.

## Proxy behavior

This skill separates two proxy paths because transcript enumeration and transcript retrieval may fail differently.

### yt-dlp proxy

Use when the channel listing itself needs a proxy.

Flags:
- `--use-yt-dlp-proxy`
- `--yt-dlp-proxy-url <proxy_url>`

### youtube-transcript-api proxy

Use when transcript retrieval itself needs a proxy.

Flags:
- `--use-transcript-proxy`
- `--transcript-http-proxy <proxy_url>`
- `--transcript-https-proxy <proxy_url>`

If only one transcript proxy URL is available, provide the same proxy to both HTTP and HTTPS arguments.

## Troubleshooting

### No videos found
- Confirm the input is a valid YouTube channel URL, usually a handle URL like `https://www.youtube.com/@name`.
- Try removing date filters to verify enumeration works.
- If the channel is large, remember `yt-dlp` may still scan many entries before filtering.

### Videos were found but transcripts were skipped
- Some videos do not expose transcripts.
- Some transcripts are region-limited, rate-limited, or temporarily unavailable.
- Try a different language preference.
- Try enabling transcript proxy support.

### Language not found
- Use a broader language fallback chain, for example `--languages en en-US en-GB`.

### Proxy issues
- Test the proxy independently with a small run.
- `socks5h://` is useful when DNS must resolve through the proxy.
- If yt-dlp works but transcript fetches fail, enable transcript proxy settings separately.

### Rate limiting or intermittent failures
- Retry later.
- Use a proxy.
- Use narrower date windows.
- Reduce run frequency for large batch jobs.

## Agent guidance

When using this skill as an agent:
- Default to saving per-video Markdown files rather than a single combined transcript document.
- Prefer explicit date filters for large channels.
- Use `--year` when the user says things like “only resources in 2026”.
- Preserve the raw transcript text; do not summarize during extraction.
- If transcript language matters, always expose the chosen language.
- If transcript retrieval fails for some videos, continue processing and report skipped items in the run summary.

## Script path

`scripts/yt_transcript_tool.py`
