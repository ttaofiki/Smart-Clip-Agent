"""
AI-powered highlight scorer using Claude API.

Reads temp/transcript.json, temp/audio_analysis.json, temp/metadata.json,
and temp/job.json. Uses Claude to score segments and select the best clips.

Usage:
  python src/tools/score_highlights.py

Output:
  temp/highlights.json
"""

import sys
import os
import json

TEMP_DIR = "temp"

# Load .env if present
def load_env():
    env_path = ".env"
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()


def read_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def build_prompt(transcript, audio, metadata, job) -> str:
    n_clips = job.get("clips", 5)
    min_dur = job.get("minDuration", 20)
    max_dur = job.get("maxDuration", 120)

    title = metadata.get("title", "Unknown")
    description = metadata.get("description", "")[:500]
    duration = metadata.get("duration", 0)
    chapters = metadata.get("chapters", [])

    # Summarize transcript (limit tokens)
    transcript_text = ""
    for seg in transcript[:200]:  # cap at 200 segments
        transcript_text += f"[{seg['start']:.1f}s-{seg['end']:.1f}s] {seg['text']}\n"

    # Summarize audio peaks
    peaks = audio.get("peaks", [])[:20]
    silences = audio.get("silences", [])[:30]
    peaks_text = ", ".join(f"{p['t']:.1f}s(rms={p['rms']})" for p in peaks)
    silences_text = ", ".join(f"{s['start']:.1f}-{s['end']:.1f}s" for s in silences)

    chapters_text = ""
    if chapters:
        chapters_text = "\n".join(f"  {c['start']:.1f}s: {c['title']}" for c in chapters)

    prompt = f"""You are a video highlight expert. Analyze this video and select the {n_clips} best highlight clips.

VIDEO METADATA:
Title: {title}
Duration: {duration:.0f}s ({duration/60:.1f} min)
Description: {description}

CHAPTERS:
{chapters_text if chapters_text else "No chapters available"}

TIMESTAMPED TRANSCRIPT:
{transcript_text}

AUDIO ENERGY PEAKS (high-energy moments):
{peaks_text if peaks_text else "No peaks detected"}

SILENCE BOUNDARIES (natural cut points):
{silences_text if silences_text else "No silences detected"}

TASK:
Select exactly {n_clips} highlight segments. Each clip must be {min_dur}–{max_dur} seconds long.

SCORING CRITERIA (total 100 points per clip):
- Hook/Opening (0-20): Strong statement, question, or hook that grabs attention
- Audio Energy (0-20): Overlaps with a high-energy audio peak
- Content Value (0-20): Key insight, revelation, quotable moment, practical tip, or climax
- Emotional Resonance (0-20): Humor, surprise, conflict, inspiration, or strong emotion
- Duration Fit (0-20): Naturally fits between {min_dur}s and {max_dur}s with clean cut points

IMPORTANT RULES:
- Prefer to start/end clips at silence boundaries for clean cuts
- Give +10 bonus if clip starts within 5s of a chapter boundary
- Clips must NOT overlap each other
- Pick segments spread throughout the video, not just the beginning
- Each clip should stand alone as an interesting excerpt

Respond with ONLY a JSON array, no other text:
[
  {{
    "rank": 1,
    "start": <float seconds>,
    "end": <float seconds>,
    "duration": <float seconds>,
    "score": <integer 0-100>,
    "title": "<short descriptive title for this clip, max 8 words>",
    "reason": "<one sentence explaining why this is a great highlight>"
  }},
  ...
]"""

    return prompt


def score_with_claude(prompt: str) -> list:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[scorer] ERROR: ANTHROPIC_API_KEY not set in environment or .env", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print("[scorer] Calling Claude to score highlights...")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    raw = message.content[0].text.strip()

    # Extract JSON array from response (handle markdown code blocks)
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    highlights = json.loads(raw)
    return highlights


def score(output_path: str = None):
    output_path = output_path or os.path.join(TEMP_DIR, "highlights.json")

    transcript = read_json(os.path.join(TEMP_DIR, "transcript.json"), default=[])
    audio = read_json(os.path.join(TEMP_DIR, "audio_analysis.json"), default={})
    metadata = read_json(os.path.join(TEMP_DIR, "metadata.json"), default={})
    job = read_json(os.path.join(TEMP_DIR, "job.json"), default={})

    if not transcript and not audio:
        print("[scorer] ERROR: Both transcript and audio analysis are empty.", file=sys.stderr)
        sys.exit(1)

    print(f"[scorer] Transcript: {len(transcript)} segments")
    print(f"[scorer] Audio peaks: {len(audio.get('peaks', []))}")
    print(f"[scorer] Chapters: {len(metadata.get('chapters', []))}")

    prompt = build_prompt(transcript, audio, metadata, job)
    highlights = score_with_claude(prompt)

    # Sort by rank
    highlights.sort(key=lambda x: x.get("rank", 999))

    os.makedirs(TEMP_DIR, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(highlights, f, indent=2)

    print(f"\n[scorer] Selected {len(highlights)} highlights:")
    for h in highlights:
        print(f"  #{h['rank']} [{h['start']:.1f}s-{h['end']:.1f}s] score={h['score']} — {h['title']}")

    print(f"\n[scorer] Saved → {output_path}")
    return output_path


if __name__ == "__main__":
    score()
