"""
Analyze audio energy and detect silence boundaries in a video file.

Uses ffmpeg to extract audio, then computes RMS energy per second and detects
silence gaps. Results are used by HighlightScorer to find natural cut points.

Usage:
  python src/tools/audio_analysis.py <video_path>

Output:
  temp/audio_analysis.json
"""

import sys
import os
import json
import subprocess
import struct
import tempfile

TEMP_DIR = "temp"
SILENCE_THRESHOLD_DB = -35   # dB below which a region is considered silence
SILENCE_MIN_DURATION = 0.8   # seconds of silence to count as a break
WINDOW_SIZE = 1.0            # seconds per energy sample


def find_ffmpeg():
    """Return path to ffmpeg, checking common Windows install locations."""
    candidates = [
        "ffmpeg",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ]
    # Also check winget install path
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
    return "ffmpeg"  # fallback — let it fail with a clear error


def extract_audio_pcm(video_path: str, ffmpeg: str) -> tuple[bytes, int, float]:
    """Extract mono 16kHz PCM from video, return (raw_bytes, sample_rate, duration)."""
    sample_rate = 16000

    # Get duration first
    result = subprocess.run(
        [ffmpeg.replace("ffmpeg", "ffprobe") if "ffmpeg.exe" in ffmpeg else "ffprobe",
         "-v", "quiet", "-print_format", "json", "-show_format", video_path],
        capture_output=True, text=True
    )
    try:
        duration = float(json.loads(result.stdout).get("format", {}).get("duration", 0))
    except Exception:
        duration = 0.0

    # Extract raw PCM
    cmd = [
        ffmpeg, "-i", video_path,
        "-vn",                      # no video
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "1",                  # mono
        "-f", "s16le",
        "pipe:1"
    ]
    proc = subprocess.run(cmd, capture_output=True)
    return proc.stdout, sample_rate, duration


def compute_rms_energy(pcm_bytes: bytes, sample_rate: int, window: float = 1.0) -> list[dict]:
    """Compute RMS energy for each window-second chunk. Returns [{t, rms}]."""
    samples_per_window = int(sample_rate * window)
    num_samples = len(pcm_bytes) // 2  # 16-bit = 2 bytes per sample
    energy = []

    positions = list(range(0, num_samples - samples_per_window, samples_per_window))
    total = len(positions)
    last_reported_pct = -1

    for idx, i in enumerate(positions):
        chunk = pcm_bytes[i * 2:(i + samples_per_window) * 2]
        if len(chunk) < 2:
            break
        samples = struct.unpack(f"<{len(chunk)//2}h", chunk)
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        t = i / sample_rate
        energy.append({"t": round(t, 2), "rms": round(rms, 2)})

        # Emit progress every 10%
        if total > 0:
            pct = int(idx / total * 100)
            if pct >= last_reported_pct + 10:
                print(f"[audio] progress: {pct}%", flush=True)
                last_reported_pct = pct

    return energy


def detect_peaks(energy: list[dict], top_n: int = 20) -> list[dict]:
    """Return the top_n highest-energy moments."""
    if not energy:
        return []
    sorted_e = sorted(energy, key=lambda x: x["rms"], reverse=True)
    return sorted_e[:top_n]


def detect_silence(video_path: str, ffmpeg: str) -> list[dict]:
    """Use ffmpeg silencedetect filter to find silence regions."""
    cmd = [
        ffmpeg, "-i", video_path,
        "-af", f"silencedetect=noise={SILENCE_THRESHOLD_DB}dB:d={SILENCE_MIN_DURATION}",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr

    silences = []
    current = {}
    for line in output.splitlines():
        if "silence_start" in line:
            try:
                t = float(line.split("silence_start:")[1].strip())
                current = {"start": round(t, 3)}
            except (IndexError, ValueError):
                pass
        elif "silence_end" in line and current:
            try:
                parts = line.split("silence_end:")[1].split("|")
                end = float(parts[0].strip())
                current["end"] = round(end, 3)
                current["duration"] = round(end - current["start"], 3)
                silences.append(current)
                current = {}
            except (IndexError, ValueError):
                pass

    return silences


def normalize_energy(energy: list[dict]) -> list[dict]:
    """Normalize RMS values to 0–100 scale."""
    if not energy:
        return energy
    max_rms = max(e["rms"] for e in energy)
    if max_rms == 0:
        return energy
    return [{"t": e["t"], "rms": round(e["rms"] / max_rms * 100, 1)} for e in energy]


def analyze(video_path: str):
    if not os.path.isfile(video_path):
        print(f"[audio] ERROR: File not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    ffmpeg = find_ffmpeg()
    print(f"[audio] Using ffmpeg: {ffmpeg}")
    print(f"[audio] Extracting audio from: {video_path}")

    pcm_bytes, sample_rate, duration = extract_audio_pcm(video_path, ffmpeg)

    if not pcm_bytes:
        print("[audio] WARNING: No audio data extracted — writing empty analysis")
        result = {"energy": [], "peaks": [], "silences": [], "duration": duration}
    else:
        print(f"[audio] Computing RMS energy (window={WINDOW_SIZE}s)...")
        energy_raw = compute_rms_energy(pcm_bytes, sample_rate, WINDOW_SIZE)
        energy = normalize_energy(energy_raw)

        peaks = detect_peaks(energy)
        print(f"[audio] Found {len(peaks)} energy peaks")

        print(f"[audio] Detecting silence boundaries...")
        silences = detect_silence(video_path, ffmpeg)
        print(f"[audio] Found {len(silences)} silence regions")

        result = {
            "duration": round(duration, 2),
            "energy": energy,
            "peaks": peaks,
            "silences": silences,
        }

    os.makedirs(TEMP_DIR, exist_ok=True)
    out_path = os.path.join(TEMP_DIR, "audio_analysis.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"[audio] Done → {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/tools/audio_analysis.py <video_path>")
        sys.exit(1)

    analyze(sys.argv[1])
