@echo off
setlocal EnableDelayedExpansion
echo.
echo  ============================================
echo    YouTube Clipping Agent -- Setup
echo  ============================================
echo.

rem ── 1. Python ───────────────────────────────────────────────────────────────
echo  [1/4] Checking Python...
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo  ERROR: Python is not installed.
    echo.
    echo  Please download and install it from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During installation, tick the box that says
    echo  "Add Python to PATH" before clicking Install Now.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo    Found: %%v

rem ── 2. Python packages ──────────────────────────────────────────────────────
echo.
echo  [2/4] Installing Python packages (may take a few minutes)...
echo.
pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo.
    echo  WARNING: One or more packages failed. Try running this manually:
    echo    pip install yt-dlp faster-whisper ffmpeg-python numpy anthropic customtkinter
    echo.
)

rem ── 3. ffmpeg ────────────────────────────────────────────────────────────────
echo.
echo  [3/4] Installing ffmpeg (video processing)...
ffmpeg -version >nul 2>&1
if !errorlevel! equ 0 (
    echo    ffmpeg is already installed.
) else (
    echo    Running: winget install Gyan.FFmpeg
    winget install Gyan.FFmpeg
    if !errorlevel! neq 0 (
        echo.
        echo  NOTE: Could not auto-install ffmpeg.
        echo  Please download it from: https://ffmpeg.org/download.html
        echo  Then add its bin\ folder to your system PATH.
    )
)

rem ── 4. API key ───────────────────────────────────────────────────────────────
echo.
echo  [4/4] Setting up API key...
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
    ) else (
        echo ANTHROPIC_API_KEY=your_api_key_here>.env
    )
    echo.
    echo  ACTION REQUIRED:
    echo  A .env file has been created. Open it and paste your Anthropic API key:
    echo.
    echo    ANTHROPIC_API_KEY=sk-ant-...
    echo.
    echo  Get your key at: https://console.anthropic.com
    echo.
    echo  Opening .env in Notepad now...
    notepad .env
) else (
    echo    .env already exists.
)

echo.
echo  ============================================
echo    Setup complete!
echo.
echo    To launch the app, double-click:
echo      run.bat
echo.
echo    Or run in terminal:
echo      python app.py
echo  ============================================
echo.
pause
