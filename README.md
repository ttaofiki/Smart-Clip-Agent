# Smart Clip Agent

An AI-powered desktop application that automatically identifies and extracts the best highlight clips from any video — YouTube, TikTok, Instagram, Twitter/X, Vimeo, or a local file.

Paste a URL (or browse to a file), choose how many clips you want, and the app handles everything: downloading, transcription, audio analysis, AI scoring, and cutting — outputting ready-to-share `.mp4` files.

---

## How It Works

Smart Clip Agent runs a multi-agent pipeline under the hood:

```
URL / Local File
      │
      ▼
 Downloader ──── or ──── FileIngestor
      │
      ▼
 Transcriber ◄──────────► AudioAnalyzer   (run in parallel)
      │                         │
      └──────────┬──────────────┘
                 ▼
          HighlightScorer  ← Claude AI virality framework
                 │
                 ▼
             Clipper  →  output/*.mp4
```

| Agent | What it does |
|---|---|
| **Downloader** | Fetches the video via `yt-dlp` from any supported platform |
| **FileIngestor** | Copies and indexes a local video file |
| **Transcriber** | Converts speech to timestamped text with `faster-whisper` |
| **AudioAnalyzer** | Detects energy peaks, silences, and RMS activity with `numpy` |
| **HighlightScorer** | Scores candidate segments using Claude AI on hook, energy, content value, emotional resonance, and duration fit |
| **Clipper** | Cuts the final clips with `ffmpeg` at silence boundaries for clean edits |

---

## Features

- **Any platform** — supports every site yt-dlp supports (YouTube, TikTok, Instagram, Twitter/X, Vimeo, and hundreds more)
- **Local files** — works with `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, and other common formats
- **AI scoring** — Claude evaluates each segment for virality potential, not just loudness
- **Clean cuts** — clip boundaries snap to silence gaps for natural-sounding edits
- **Chapter-aware** — chapters from the video metadata get a bonus score for alignment
- **Desktop GUI** — dark-mode interface with a real-time progress bar, no terminal needed
- **Configurable** — set clip count, minimum and maximum clip duration per job

---

## Requirements

- **Python 3.9+**
- **Node.js 18+**
- **ffmpeg** (auto-installed by setup on Windows via winget)
- **Anthropic API key** — get one free at [console.anthropic.com](https://console.anthropic.com)

---

## Installation (Windows)

1. Clone the repo:
   ```
   git clone https://github.com/ttaofiki/Smart-Clip-Agent.git
   cd Smart-Clip-Agent
   ```

2. Run the one-click setup script:
   ```
   setup.bat
   ```
   This installs Python packages, ffmpeg, and creates a `.env` file where you paste your API key.

3. Add your Anthropic API key to `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

4. Launch the app:
   ```
   run.bat
   ```
   Or directly: `python app.py`

---

## Installation (macOS / Linux)

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install ffmpeg (macOS)
brew install ffmpeg

# Install ffmpeg (Ubuntu/Debian)
sudo apt install ffmpeg

# Add your API key
cp .env.example .env
# Edit .env and paste your ANTHROPIC_API_KEY

# Launch
python app.py
```

---

## Usage

1. **Paste a URL** into the URL field — or click **Browse** to pick a local video file
2. Set the number of clips, minimum duration, and maximum duration
3. Click **Run**
4. Watch the live log and progress bar as each pipeline stage completes
5. Find your clips in the `output/` folder when done

---

## Output

Clips are saved to `output/` as:
```
output/<descriptive_title>_clip_1.mp4
output/<descriptive_title>_clip_2.mp4
...
```

Each clip is named after the AI-generated title for that highlight segment.

---

## Project Structure

```
Smart_Clip_Agent/
├── app.py                  # Desktop GUI (customtkinter)
├── main.js                 # Node.js CLI entry point
├── src/
│   └── tools/
│       ├── download.py     # yt-dlp downloader / local file ingestor
│       ├── transcribe.py   # Speech-to-text via faster-whisper
│       ├── audio_analysis.py  # Energy peaks & silence detection
│       ├── score_highlights.py  # Claude AI highlight scoring
│       └── clip.py         # ffmpeg clip cutter
├── temp/                   # Pipeline working files (auto-created, gitignored)
├── output/                 # Final clips (gitignored)
├── requirements.txt
├── setup.bat               # Windows one-click setup
├── run.bat                 # Windows launcher
└── .env.example            # API key template
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| GUI | Python · customtkinter |
| Video download | yt-dlp |
| Speech-to-text | faster-whisper (Whisper base model) |
| Audio analysis | numpy · ffmpeg-python |
| AI scoring | Anthropic Claude API |
| Video cutting | ffmpeg-python |
| Agent orchestration | Claude Flow (Ruflo) |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Never commit your `.env` file — it is gitignored by default.

---

## License

MIT
