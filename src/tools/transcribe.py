"""
Transcribe a video file to a timestamped JSON transcript using faster-whisper.

Usage:
  python src/tools/transcribe.py <video_path>

Output:
  temp/transcript.json — list of {text, start, end} segments
"""

import sys
import os
import json

TEMP_DIR = "temp"

MODEL_SIZE = "small"  # small is fast enough for highlight detection; medium is 4x slower on CPU


def get_model_size(video_path: str) -> str:
    return MODEL_SIZE


def transcribe(video_path: str):
    from faster_whisper import WhisperModel

    if not os.path.isfile(video_path):
        print(f"[transcribe] ERROR: File not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    model_size = get_model_size(video_path)
    print(f"[transcribe] Using model: {model_size}")
    print(f"[transcribe] Loading model (first run downloads weights ~150–500 MB)...")

    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print(f"[transcribe] Transcribing: {video_path}")
    segments, info = model.transcribe(
        video_path,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,        # skip silent regions
        vad_parameters={"min_silence_duration_ms": 500},
    )

    print(f"[transcribe] Detected language: {info.language} (prob={info.language_probability:.2f})")

    total_dur = info.duration  # total audio duration in seconds
    transcript = []
    last_reported_pct = -1

    for seg in segments:
        entry = {
            "text": seg.text.strip(),
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
        }
        if seg.words:
            entry["words"] = [
                {"word": w.word, "start": round(w.start, 3), "end": round(w.end, 3)}
                for w in seg.words
            ]
        transcript.append(entry)
        print(f"  [{entry['start']:.1f}s → {entry['end']:.1f}s] {entry['text'][:80]}")

        # Emit a progress line every 5%
        if total_dur and total_dur > 0:
            pct = min(int(seg.end / total_dur * 100), 99)
            if pct >= last_reported_pct + 5:
                print(f"[transcribe] progress: {pct}%", flush=True)
                last_reported_pct = pct

    os.makedirs(TEMP_DIR, exist_ok=True)
    out_path = os.path.join(TEMP_DIR, "transcript.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)

    print(f"\n[transcribe] Done — {len(transcript)} segments → {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/tools/transcribe.py <video_path>")
        sys.exit(1)

    transcribe(sys.argv[1])
