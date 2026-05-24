#!/usr/bin/env node
/**
 * Smart Clip Agent — main entry point
 *
 * Usage:
 *   node main.js --url "https://youtube.com/watch?v=..."
 *   node main.js --file "path/to/video.mp4"
 *   node main.js --url "..." --clips 3 --min-duration 30 --max-duration 90
 */

import { execSync } from 'child_process';
import { writeFileSync, mkdirSync, existsSync } from 'fs';
import { resolve } from 'path';

// ── Parse CLI args ────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const key = argv[i];
    const val = argv[i + 1];
    if (key === '--url') { args.url = val; i++; }
    else if (key === '--file') { args.file = resolve(val); i++; }
    else if (key === '--clips') { args.clips = parseInt(val, 10); i++; }
    else if (key === '--min-duration') { args.minDuration = parseInt(val, 10); i++; }
    else if (key === '--max-duration') { args.maxDuration = parseInt(val, 10); i++; }
    else if (key === '--help' || key === '-h') { printHelp(); process.exit(0); }
  }
  return args;
}

function printHelp() {
  console.log(`
Smart Clip Agent

Usage:
  node main.js --url  <video-url>     Download from any platform and clip highlights
  node main.js --file <video-path>    Clip highlights from a local video file

Options:
  --clips         N    Number of clips to extract (default: 5)
  --min-duration  S    Minimum clip length in seconds (default: 20)
  --max-duration  S    Maximum clip length in seconds (default: 120)
  --help               Show this help

Examples:
  node main.js --url "https://youtube.com/watch?v=dQw4w9WgXcQ" --clips 3
  node main.js --file "C:/Videos/lecture.mp4" --clips 5 --min-duration 30
`);
}

// ── Validate environment ──────────────────────────────────────────────────────

function checkDependencies() {
  const checks = [
    { cmd: 'python --version', name: 'Python' },
    { cmd: 'ffmpeg -version', name: 'ffmpeg' },
  ];

  const missing = [];
  for (const { cmd, name } of checks) {
    try {
      execSync(cmd, { stdio: 'pipe' });
    } catch {
      missing.push(name);
    }
  }

  if (missing.length > 0) {
    console.error(`\n[ERROR] Missing dependencies: ${missing.join(', ')}`);
    console.error('Run the following to install:');
    if (missing.includes('ffmpeg')) {
      console.error('  winget install Gyan.FFmpeg');
    }
    if (missing.includes('Python')) {
      console.error('  Download Python from https://python.org');
    }
    console.error('\nThen re-run this command.');
    process.exit(1);
  }
}

function checkPythonPackages() {
  const packages = ['yt_dlp', 'faster_whisper', 'ffmpeg'];
  const missing = [];
  for (const pkg of packages) {
    try {
      execSync(`python -c "import ${pkg}"`, { stdio: 'pipe' });
    } catch {
      missing.push(pkg.replace('_', '-'));
    }
  }
  if (missing.length > 0) {
    console.error(`\n[ERROR] Missing Python packages: ${missing.join(', ')}`);
    console.error(`Install with: pip install ${missing.join(' ')}`);
    process.exit(1);
  }
}

// ── Setup job ─────────────────────────────────────────────────────────────────

function setupJob(args) {
  mkdirSync('temp', { recursive: true });
  mkdirSync('output', { recursive: true });

  const job = {
    input: args.url || args.file,
    inputType: args.url ? 'url' : 'file',
    clips: args.clips ?? 5,
    minDuration: args.minDuration ?? 20,
    maxDuration: args.maxDuration ?? 120,
    startedAt: new Date().toISOString(),
  };

  writeFileSync('temp/job.json', JSON.stringify(job, null, 2));
  return job;
}

// ── Pipeline ──────────────────────────────────────────────────────────────────

function runStep(label, cmd) {
  console.log(`\n[${label}] Running: ${cmd}`);
  try {
    execSync(cmd, { stdio: 'inherit', shell: true });
    console.log(`[${label}] ✓ Done`);
    return true;
  } catch (err) {
    console.error(`[${label}] ✗ Failed: ${err.message}`);
    return false;
  }
}

function findVideoFile() {
  try {
    const files = execSync('python -c "import glob, json; files=glob.glob(\'temp/video.*\'); print(files[0] if files else \'\')"', { encoding: 'utf8' }).trim();
    return files || null;
  } catch {
    return null;
  }
}

function runFallbackPipeline(job) {
  console.log('\n━━━ Fallback Sequential Pipeline ━━━\n');

  // Step 1: Download or ingest
  const downloadCmd = job.inputType === 'url'
    ? `python src/tools/download.py "${job.input}"`
    : `python src/tools/download.py --file "${job.input}"`;

  if (!runStep('Download', downloadCmd)) return;

  const videoPath = findVideoFile();
  if (!videoPath) {
    console.error('[ERROR] Could not find video in temp/ after download.');
    return;
  }

  // Steps 2+3: Transcribe and analyze audio (sequential in fallback)
  runStep('Transcribe', `python src/tools/transcribe.py "${videoPath}"`);
  runStep('AudioAnalysis', `python src/tools/audio_analysis.py "${videoPath}"`);

  // Step 4: Score highlights using Claude
  if (!existsSync('temp/transcript.json') && !existsSync('temp/audio_analysis.json')) {
    console.error('[ERROR] No transcript or audio analysis available for scoring.');
    return;
  }

  runStep('HighlightScore', `python src/tools/score_highlights.py`);

  // Step 5: Cut clips
  if (!existsSync('temp/highlights.json')) {
    console.error('[ERROR] No highlights.json found — cannot cut clips.');
    return;
  }

  runStep('Clip', `python src/tools/clip.py "${videoPath}" temp/highlights.json`);

  console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('  Pipeline complete. Check output/');
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');
}

// ── Main ──────────────────────────────────────────────────────────────────────

const args = parseArgs(process.argv);

if (!args.url && !args.file) {
  console.error('[ERROR] Provide --url or --file\n');
  printHelp();
  process.exit(1);
}

checkDependencies();
checkPythonPackages();

const job = setupJob(args);

console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
console.log('  Smart Clip Agent');
console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
console.log(`  Input:     ${job.input}`);
console.log(`  Clips:     ${job.clips}`);
console.log(`  Duration:  ${job.minDuration}s – ${job.maxDuration}s`);
console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');

runFallbackPipeline(job);
