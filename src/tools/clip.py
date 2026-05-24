"""
Cut video clips from a source video using timestamps from highlights.json.

Uses ffmpeg stream copy for speed (no re-encode). Falls back to re-encode
if the source format doesn't support clean stream copy cuts.

Usage:
  python src/tools/clip.py <video_path> <highlights_json>

Output:
  output/<sanitized_title>_clip_N.mp4 for each highlight
"""

import sys
import os
import json
import subprocess
import re

OUTPUT_DIR = "output"


def find_ffmpeg():
    candidates = [
        "ffmpeg",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ]
    appdata = os.environ.get("LOCALAPPDATA", "")
    if appdata:
        candidates.append(os.path.join(appdata, "Microsoft", "WinGet", "Packages",
                                       "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe",
                                       "ffmpeg-8.1.1-full_build", "bin", "ffmpeg.exe"))
    for c in candidates:
        try:
            subprocess.run([c, "-version"], capture_output=True, check=True)
            return c
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return "ffmpeg"


def sanitize(name: str, max_len: int = 50) -> str:
    """Make a string safe to use as a filename."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    name = re.sub(r'[^\w\-]', '', name)
    return name[:max_len] or "clip"


def cut_clip(ffmpeg: str, video_path: str, start: float, end: float,
             out_path: str, use_copy: bool = True) -> bool:
    """Cut a single clip. Returns True on success."""
    duration = end - start
    if duration <= 0:
        print(f"  [clip] SKIP: zero/negative duration ({start:.1f}→{end:.1f})")
        return False

    if use_copy:
        cmd = [
            ffmpeg,
            "-ss", str(start),
            "-i", video_path,
            "-t", str(duration),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-y", out_path
        ]
    else:
        cmd = [
            ffmpeg,
            "-ss", str(start),
            "-i", video_path,
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-y", out_path
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False

    # Verify output file exists and is non-empty
    return os.path.isfile(out_path) and os.path.getsize(out_path) > 1024


def clip(video_path: str, highlights_path: str):
    if not os.path.isfile(video_path):
        print(f"[clip] ERROR: Video not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(highlights_path):
        print(f"[clip] ERROR: Highlights JSON not found: {highlights_path}", file=sys.stderr)
        sys.exit(1)

    with open(highlights_path, "r", encoding="utf-8") as f:
        highlights = json.load(f)

    if not highlights:
        print("[clip] No highlights to cut.")
        return []

    ffmpeg = find_ffmpeg()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_clips = len(highlights)
    created = []
    for i, h in enumerate(highlights, 1):
        print(f"[clip] progress: {i-1}/{total_clips}", flush=True)
        start = h.get("start", 0)
        end = h.get("end", 0)
        title = h.get("title", f"clip_{i}")
        rank = h.get("rank", i)
        score = h.get("score", 0)

        safe_title = sanitize(title)
        out_name = f"{safe_title}_clip{rank:02d}.mp4"
        out_path = os.path.join(OUTPUT_DIR, out_name)

        print(f"\n[clip] {rank}. \"{title}\" [{start:.1f}s → {end:.1f}s] (score={score})")
        print(f"  → {out_path}")

        # Try stream copy first (fast), fall back to re-encode
        success = cut_clip(ffmpeg, video_path, start, end, out_path, use_copy=True)
        if not success:
            print(f"  [clip] Stream copy failed, retrying with re-encode...")
            success = cut_clip(ffmpeg, video_path, start, end, out_path, use_copy=False)

        if success:
            size_mb = os.path.getsize(out_path) / 1024 / 1024
            print(f"  [clip] ✓ Saved ({size_mb:.1f} MB)")
            created.append({
                "rank": rank,
                "title": title,
                "file": out_path,
                "size_mb": round(size_mb, 2),
                "duration": round(end - start, 1),
                "score": score,
            })
        else:
            print(f"  [clip] ✗ FAILED to create clip", file=sys.stderr)

    print(f"\n[clip] Done — {len(created)}/{len(highlights)} clips created in {OUTPUT_DIR}/")

    # Write summary
    summary_path = os.path.join("temp", "clips_summary.json")
    with open(summary_path, "w") as f:
        json.dump(created, f, indent=2)

    return created


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python src/tools/clip.py <video_path> <highlights_json>")
        sys.exit(1)

    clip(sys.argv[1], sys.argv[2])
