"""
Download a YouTube video (or ingest a local file) into temp/.

Usage:
  python src/tools/download.py "<youtube_url>"
  python src/tools/download.py --file "path/to/video.mp4"
"""

import sys
import os
import json
import shutil
import glob

TEMP_DIR = "temp"


def sanitize_filename(name: str) -> str:
    keep = set(" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_()")
    return "".join(c if c in keep else "_" for c in name).strip()


def _ydl_progress_hook(d):
    """Emit a parseable progress line for the GUI progress bar."""
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
        downloaded = d.get("downloaded_bytes", 0)
        if total and total > 0:
            pct = downloaded / total * 100
            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            print(f"[download] progress: {pct:.1f}%  {speed}  ETA {eta}", flush=True)
    elif d["status"] == "finished":
        print("[download] progress: 100%", flush=True)
        print("[download] Processing / merging streams...", flush=True)


def download_youtube(url: str):
    import yt_dlp

    os.makedirs(TEMP_DIR, exist_ok=True)

    ydl_opts = {
        "outtmpl": os.path.join(TEMP_DIR, "video.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
        "noprogress": True,          # suppress yt-dlp's own bar; we use the hook
        "progress_hooks": [_ydl_progress_hook],
        "writeinfojson": False,
    }

    print(f"[download] Fetching: {url}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Build metadata
    chapters = []
    if info.get("chapters"):
        for ch in info["chapters"]:
            chapters.append({
                "title": ch.get("title", ""),
                "start": ch.get("start_time", 0),
                "end": ch.get("end_time", 0),
            })

    metadata = {
        "title": info.get("title", "Untitled"),
        "duration": info.get("duration", 0),
        "description": (info.get("description") or "")[:2000],
        "chapters": chapters,
        "uploader": info.get("uploader", ""),
        "url": url,
        "ext": info.get("ext", "mp4"),
    }

    meta_path = os.path.join(TEMP_DIR, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"[download] Saved metadata → {meta_path}")
    print(f"[download] Title: {metadata['title']}")
    print(f"[download] Duration: {metadata['duration']}s  Chapters: {len(chapters)}")

    # Confirm video file
    video_files = glob.glob(os.path.join(TEMP_DIR, "video.*"))
    if not video_files:
        print("[download] ERROR: video file not found after download", file=sys.stderr)
        sys.exit(1)

    print(f"[download] Video file: {video_files[0]}")
    return video_files[0]


def ingest_local(file_path: str):
    if not os.path.isfile(file_path):
        print(f"[ingest] ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(TEMP_DIR, exist_ok=True)

    ext = os.path.splitext(file_path)[1].lower()
    dest = os.path.join(TEMP_DIR, f"video{ext}")

    if os.path.abspath(file_path) != os.path.abspath(dest):
        print(f"[ingest] Copying {file_path} → {dest}")
        shutil.copy2(file_path, dest)
    else:
        print(f"[ingest] File already in temp/: {dest}")

    # Probe duration with ffprobe if available
    duration = 0
    try:
        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", file_path],
            capture_output=True, text=True
        )
        probe = json.loads(result.stdout)
        duration = float(probe.get("format", {}).get("duration", 0))
    except Exception:
        pass

    metadata = {
        "title": os.path.splitext(os.path.basename(file_path))[0],
        "duration": duration,
        "description": "",
        "chapters": [],
        "uploader": "",
        "url": file_path,
        "ext": ext.lstrip("."),
    }

    meta_path = os.path.join(TEMP_DIR, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"[ingest] Metadata saved → {meta_path}")
    print(f"[ingest] Video file: {dest}")
    return dest


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print("Usage: python src/tools/download.py <url>")
        print("       python src/tools/download.py --file <path>")
        sys.exit(1)

    if args[0] == "--file":
        if len(args) < 2:
            print("ERROR: --file requires a path", file=sys.stderr)
            sys.exit(1)
        ingest_local(args[1])
    else:
        download_youtube(args[0])
