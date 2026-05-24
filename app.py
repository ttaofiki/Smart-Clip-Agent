"""
YouTube Clipping Agent — Desktop GUI
Run: python app.py
"""

try:
    import customtkinter as ctk
except ImportError:
    import sys, subprocess
    print("Installing customtkinter...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "customtkinter"])
    import customtkinter as ctk

from tkinter import filedialog, messagebox
import subprocess
import threading
import re
import os
import json
import glob
from datetime import datetime

# Keep relative paths (temp/, output/, src/) working regardless of launch location
os.chdir(os.path.dirname(os.path.abspath(__file__)))

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Progress line patterns emitted by the Python tools ────────────────────────
# Each tuple: (compiled regex, function that extracts a 0.0–100.0 float)
_PROGRESS_PATTERNS = [
    # [download] progress: 45.3%  1.23MiB/s  ETA 00:30
    (re.compile(r'\[download\] progress:\s*([\d.]+)%'),
     lambda m: float(m.group(1))),
    # [transcribe] progress: 45%
    (re.compile(r'\[transcribe\] progress:\s*(\d+)%'),
     lambda m: float(m.group(1))),
    # [audio] progress: 60%
    (re.compile(r'\[audio\] progress:\s*(\d+)%'),
     lambda m: float(m.group(1))),
    # [clip] progress: 2/5
    (re.compile(r'\[clip\] progress:\s*(\d+)/(\d+)'),
     lambda m: int(m.group(1)) / max(int(m.group(2)), 1) * 100),
]


def _extract_progress(line: str):
    """Return 0.0–100.0 if the line contains a progress marker, else None."""
    for pattern, extractor in _PROGRESS_PATTERNS:
        m = pattern.search(line)
        if m:
            return extractor(m)
    return None


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Smart Clip Agent")
        self.geometry("740x760")
        self.minsize(620, 680)
        self._build()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self):
        # Header
        ctk.CTkLabel(self, text="Smart Clip Agent",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(20, 2))
        ctk.CTkLabel(self, text="AI-powered highlight extraction from any video or social media platform",
                     font=ctk.CTkFont(size=12), text_color="gray60").pack(pady=(0, 14))

        # ── Input panel ───────────────────────────────────────────────────────
        src = ctk.CTkFrame(self)
        src.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(src, text="INPUT SOURCE",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray60").pack(anchor="w", padx=14, pady=(12, 6))

        self.mode = ctk.StringVar(value="url")
        radio_row = ctk.CTkFrame(src, fg_color="transparent")
        radio_row.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkRadioButton(radio_row, text="YouTube URL",
                           variable=self.mode, value="url",
                           command=self._on_mode).pack(side="left", padx=(0, 24))
        ctk.CTkRadioButton(radio_row, text="Local Video File",
                           variable=self.mode, value="file",
                           command=self._on_mode).pack(side="left")

        input_row = ctk.CTkFrame(src, fg_color="transparent")
        input_row.pack(fill="x", padx=14, pady=(0, 14))
        input_row.columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(input_row, height=38,
                                   placeholder_text="https://www.youtube.com/watch?v=...",
                                   font=ctk.CTkFont(size=12))
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.browse_btn = ctk.CTkButton(input_row, text="Browse", width=90, height=38,
                                         fg_color="gray35", hover_color="gray45",
                                         state="disabled", command=self._browse)
        self.browse_btn.grid(row=0, column=1)

        # ── Settings panel ────────────────────────────────────────────────────
        cfg = ctk.CTkFrame(self)
        cfg.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(cfg, text="CLIP SETTINGS",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray60").pack(anchor="w", padx=14, pady=(12, 8))

        row = ctk.CTkFrame(cfg, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 14))

        for label, default, attr in [
            ("Number of clips", "5",   "clips_var"),
            ("Min duration (s)", "20", "min_var"),
            ("Max duration (s)", "120","max_var"),
        ]:
            cell = ctk.CTkFrame(row, fg_color="transparent")
            cell.pack(side="left", padx=(0, 32))
            ctk.CTkLabel(cell, text=label, font=ctk.CTkFont(size=12)).pack(anchor="w")
            var = ctk.StringVar(value=default)
            setattr(self, attr, var)
            ctk.CTkEntry(cell, textvariable=var, width=80, height=34).pack(anchor="w", pady=(4, 0))

        # ── Start button ──────────────────────────────────────────────────────
        self.start_btn = ctk.CTkButton(self, text="▶   START CLIPPING", height=46,
                                        font=ctk.CTkFont(size=15, weight="bold"),
                                        command=self._start)
        self.start_btn.pack(fill="x", padx=20, pady=(4, 8))

        # ── Progress section ──────────────────────────────────────────────────
        prog_frame = ctk.CTkFrame(self)
        prog_frame.pack(fill="x", padx=20, pady=(0, 8))

        # Row 1 — overall pipeline bar
        row1 = ctk.CTkFrame(prog_frame, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(10, 4))
        row1.columnconfigure(0, weight=1)

        ctk.CTkLabel(row1, text="Overall",
                     font=ctk.CTkFont(size=11), text_color="gray60",
                     width=58, anchor="w").grid(row=0, column=0, sticky="w")
        self.overall_bar = ctk.CTkProgressBar(row1, height=12)
        self.overall_bar.grid(row=0, column=1, sticky="ew", padx=(6, 8))
        row1.columnconfigure(1, weight=1)
        self.overall_pct_lbl = ctk.CTkLabel(row1, text="0%",
                                             font=ctk.CTkFont(size=11),
                                             width=36, anchor="e")
        self.overall_pct_lbl.grid(row=0, column=2)
        self.overall_bar.set(0)

        # Row 2 — step bar (shows download %, transcription %, etc.)
        row2 = ctk.CTkFrame(prog_frame, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(4, 4))
        row2.columnconfigure(1, weight=1)

        self.step_name_lbl = ctk.CTkLabel(row2, text="Ready",
                                           font=ctk.CTkFont(size=11), text_color="gray60",
                                           width=58, anchor="w")
        self.step_name_lbl.grid(row=0, column=0, sticky="w")
        self.step_bar = ctk.CTkProgressBar(row2, height=12,
                                            progress_color=("#2ecc71", "#27ae60"))
        self.step_bar.grid(row=0, column=1, sticky="ew", padx=(6, 8))
        self.step_pct_lbl = ctk.CTkLabel(row2, text="",
                                          font=ctk.CTkFont(size=11),
                                          width=36, anchor="e")
        self.step_pct_lbl.grid(row=0, column=2)
        self.step_bar.set(0)

        # Row 3 — status text
        self.status_lbl = ctk.CTkLabel(prog_frame, text="",
                                        font=ctk.CTkFont(size=11), text_color="gray50")
        self.status_lbl.pack(anchor="w", padx=12, pady=(0, 10))

        # ── Log ───────────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="OUTPUT LOG",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray60").pack(anchor="w", padx=20)

        self.log = ctk.CTkTextbox(self,
                                   font=ctk.CTkFont(family="Courier New", size=11),
                                   state="disabled")
        self.log.pack(fill="both", expand=True, padx=20, pady=(4, 8))

        # ── Open output folder ────────────────────────────────────────────────
        self.open_btn = ctk.CTkButton(
            self, text="📁  Open Output Folder", height=36,
            fg_color="gray28", hover_color="gray38",
            command=lambda: os.startfile(os.path.abspath("output"))
        )
        self.open_btn.pack(fill="x", padx=20, pady=(0, 16))

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_mode(self):
        if self.mode.get() == "url":
            self.entry.configure(
                placeholder_text="https://www.youtube.com/watch?v=...")
            self.browse_btn.configure(state="disabled",
                                       fg_color="gray35", hover_color="gray45")
        else:
            self.entry.configure(placeholder_text="C:\\Users\\...\\video.mp4  (or .mkv, .avi, .mov, .webm)")
            self.browse_btn.configure(state="normal",
                                       fg_color=["#3a7ebf", "#1f538d"],
                                       hover_color=["#325882", "#14375e"])

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select a video file",
            filetypes=[
                ("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.m4v"),
                ("All files", "*.*"),
            ]
        )
        if path:
            self.entry.delete(0, "end")
            self.entry.insert(0, path)

    # ── Thread-safe helpers ───────────────────────────────────────────────────

    def _log(self, text: str):
        def _do():
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(0, _do)

    def _set_overall(self, value: float, status: str = ""):
        """value = 0.0–1.0"""
        pct = int(value * 100)
        self.after(0, self.overall_bar.set, value)
        self.after(0, lambda: self.overall_pct_lbl.configure(text=f"{pct}%"))
        if status:
            self.after(0, lambda: self.status_lbl.configure(text=status))

    def _set_step(self, value: float, label: str = ""):
        """value = 0.0–1.0, label = short step name shown left of bar"""
        pct_str = f"{int(value * 100)}%" if value > 0 else ""
        self.after(0, self.step_bar.set, value)
        self.after(0, lambda: self.step_pct_lbl.configure(text=pct_str))
        if label:
            self.after(0, lambda: self.step_name_lbl.configure(text=label))

    # ── Validation ────────────────────────────────────────────────────────────

    def _check_api_key(self) -> bool:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key and os.path.isfile(".env"):
            with open(".env") as f:
                for line in f:
                    if line.strip().startswith("ANTHROPIC_API_KEY="):
                        key = line.strip().split("=", 1)[1].strip()
        if not key or key == "your_api_key_here":
            messagebox.showerror(
                "API Key Missing",
                "ANTHROPIC_API_KEY is not set.\n\n"
                "Open the .env file in the project folder and add:\n"
                "ANTHROPIC_API_KEY=sk-ant-...\n\n"
                "Get your key at: https://console.anthropic.com"
            )
            return False
        return True

    # ── Start ─────────────────────────────────────────────────────────────────

    def _start(self):
        inp = self.entry.get().strip()
        if not inp:
            messagebox.showerror("Missing input",
                                  "Paste a YouTube URL or select a local video file.")
            return
        if not self._check_api_key():
            return
        try:
            clips = int(self.clips_var.get())
            mn    = int(self.min_var.get())
            mx    = int(self.max_var.get())
            assert 1 <= clips <= 20
            assert mn >= 5
            assert mx > mn
        except (ValueError, AssertionError):
            messagebox.showerror("Invalid settings",
                                  "• Clips: 1–20\n"
                                  "• Min duration ≥ 5 seconds\n"
                                  "• Max duration must be greater than Min")
            return

        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.start_btn.configure(state="disabled", text="⏳  Running...")
        self._set_overall(0, "Starting...")
        self._set_step(0, "")

        threading.Thread(
            target=self._pipeline, args=(inp, clips, mn, mx), daemon=True
        ).start()

    # ── Pipeline step runner ─────────────────────────────────────────────────

    def _step(self, label: str, short: str, cmd: str,
              overall_start: float, overall_end: float) -> bool:
        """
        Run one pipeline step.
        - label      : full label shown in log
        - short      : short name shown in the step bar (≤12 chars)
        - overall_*  : the range of the overall bar this step occupies (0.0–1.0)
        """
        self._set_overall(overall_start, f"{label}...")
        self._set_step(0, short)
        self._log(f"\n▶  {label}")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=True,
            bufsize=1,
            env=env,
        )

        for line in proc.stdout:
            stripped = line.rstrip()
            if not stripped:
                continue

            pct = _extract_progress(stripped)
            if pct is not None:
                # Update the step bar with real % from the tool
                self._set_step(pct / 100, short)
                # Also nudge overall bar within this step's range
                span = overall_end - overall_start
                self._set_overall(overall_start + span * pct / 100)
                # Only log non-spammy progress lines (skip bare % updates)
                if "progress:" not in stripped:
                    self._log("   " + stripped)
            else:
                self._log("   " + stripped)

        proc.wait()

        if proc.returncode != 0:
            self._log(f"   ✗  Failed (exit code {proc.returncode})")
            self._set_step(0, short)
            return False

        self._set_step(1.0, short)
        self._set_overall(overall_end)
        self._log("   ✓  Done")
        return True

    # ── Pipeline (background thread) ─────────────────────────────────────────

    def _pipeline(self, inp: str, clips: int, mn: int, mx: int):
        os.makedirs("temp",   exist_ok=True)
        os.makedirs("output", exist_ok=True)

        is_url = inp.startswith("http")
        with open("temp/job.json", "w") as f:
            json.dump({
                "input":       inp,
                "inputType":   "url" if is_url else "file",
                "clips":       clips,
                "minDuration": mn,
                "maxDuration": mx,
                "startedAt":   datetime.now().isoformat(),
            }, f, indent=2)

        # ── Step 1: Download / ingest  (overall 0% → 18%) ─────────────────
        cmd1 = (f'python src/tools/download.py "{inp}"' if is_url
                else f'python src/tools/download.py --file "{inp}"')
        if not self._step(
            "Downloading video" if is_url else "Loading local video",
            "Download", cmd1, 0.00, 0.18
        ):
            return self._finish(False)

        videos = glob.glob("temp/video.*")
        if not videos:
            self._log("\n✗  No video found in temp/ — download may have failed.")
            return self._finish(False)
        video = videos[0]

        # ── Step 2: Transcribe  (overall 18% → 55%) ───────────────────────
        self._step(
            "Transcribing speech  (this may take a few minutes)",
            "Transcribe",
            f'python src/tools/transcribe.py "{video}"',
            0.18, 0.55
        )

        # ── Step 3: Audio analysis  (overall 55% → 72%) ───────────────────
        self._step(
            "Analyzing audio energy",
            "Audio",
            f'python src/tools/audio_analysis.py "{video}"',
            0.55, 0.72
        )

        # ── Step 4: AI scoring  (overall 72% → 88%) ───────────────────────
        if not self._step(
            "Scoring highlights with Claude AI",
            "AI Score",
            "python src/tools/score_highlights.py",
            0.72, 0.88
        ):
            return self._finish(False)

        # ── Step 5: Cut clips  (overall 88% → 100%) ───────────────────────
        if not self._step(
            "Cutting clips",
            "Cutting",
            f'python src/tools/clip.py "{video}" temp/highlights.json',
            0.88, 1.00
        ):
            return self._finish(False)

        self._finish(True)

    def _finish(self, ok: bool):
        if ok:
            self._set_overall(1.0, "✓  All done!")
            self._set_step(1.0, "Done")
            self._log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self._log("  ✓  Pipeline complete!")
            self._log("  Clips are in the  output/  folder.")
            self._log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.after(800, lambda: os.startfile(os.path.abspath("output")))
        else:
            self._set_overall(0, "✗  Failed — see log above")
            self._set_step(0, "")

        self.after(0, lambda: self.start_btn.configure(
            state="normal", text="▶   START CLIPPING"
        ))


if __name__ == "__main__":
    app = App()
    app.mainloop()
