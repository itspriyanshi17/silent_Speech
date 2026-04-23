"""
Download Sample Video Clips for Lip Reading Demo

Downloads short 4-second clips from YouTube TED talks that closely match the LRS3
training data domain (frontal face, good lighting, clear English speech, 25fps).

Usage:
    pip install yt-dlp
    python download_samples.py

The clips are saved to sample_videos/ with a manifest.json containing metadata.
Requires: yt-dlp and ffmpeg (for segment extraction and re-encoding at 25fps).
"""

import os
import sys
import json
import subprocess
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "sample_videos")

# ─── Sample clips from TED talks (public, frontal face, clear English speech) ───
# Each entry defines a 4-second segment to download at 25fps.
SAMPLE_CLIPS = [
    {
        "url": "https://www.youtube.com/watch?v=8jPQjjsBbIc",
        "start": 65,
        "duration": 4,
        "name": "ted_talk_1",
        "description": "TED Talk - Clear frontal speech",
        "source": "TED Talk (YouTube)",
    },
    {
        "url": "https://www.youtube.com/watch?v=8jPQjjsBbIc",
        "start": 120,
        "duration": 4,
        "name": "ted_talk_2",
        "description": "TED Talk - Another clear segment",
        "source": "TED Talk (YouTube)",
    },
    {
        "url": "https://www.youtube.com/watch?v=arj7oStGLkU",
        "start": 30,
        "duration": 4,
        "name": "ted_talk_3",
        "description": "TED Talk - Well-lit speaker",
        "source": "TED Talk (YouTube)",
    },
    {
        "url": "https://www.youtube.com/watch?v=arj7oStGLkU",
        "start": 90,
        "duration": 4,
        "name": "ted_talk_4",
        "description": "TED Talk - Another speaking segment",
        "source": "TED Talk (YouTube)",
    },
    {
        "url": "https://www.youtube.com/watch?v=UF8uR6Z6KLc",
        "start": 45,
        "duration": 4,
        "name": "ted_talk_5",
        "description": "TED Talk - Steve Jobs presentation",
        "source": "TED Talk (YouTube)",
    },
]


def check_dependencies():
    """Check if yt-dlp and ffmpeg are installed."""
    if not shutil.which("yt-dlp"):
        print("  ⬇ yt-dlp not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)

    if not shutil.which("ffmpeg"):
        print("  ✗ ffmpeg not found! Please install ffmpeg:")
        print("    Windows: winget install ffmpeg  or  choco install ffmpeg")
        print("    Mac:     brew install ffmpeg")
        print("    Linux:   sudo apt install ffmpeg")
        sys.exit(1)

    print("  ✓ yt-dlp and ffmpeg found.")


def download_clip(clip_info, output_dir):
    """Download a specific 4-second clip segment from YouTube at 25fps."""
    output_path = os.path.join(output_dir, f"{clip_info['name']}.mp4")

    if os.path.exists(output_path):
        size_kb = os.path.getsize(output_path) / 1024
        # If file is too large (> 5MB), it's probably the full video — re-download
        if size_kb < 5000:
            print(f"  ✓ Already exists ({size_kb:.0f} KB): {clip_info['name']}.mp4")
            return output_path
        else:
            print(f"  ⚠ {clip_info['name']}.mp4 is too large ({size_kb:.0f} KB), re-downloading...")
            os.remove(output_path)

    start = clip_info["start"]
    duration = clip_info["duration"]
    end = start + duration

    print(f"  ⬇ Downloading: {clip_info['name']} ({duration}s, from {start}s to {end}s)...")

    # Use yt-dlp --download-sections to download ONLY the needed segment
    # This avoids downloading the entire video
    temp_path = os.path.join(output_dir, f"_temp_{clip_info['name']}.mp4")

    try:
        # Step 1: Download only the relevant section using yt-dlp
        section_spec = f"*{start}-{end}"
        cmd_download = [
            "yt-dlp",
            "--no-playlist",
            "--download-sections", section_spec,
            "-f", "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--force-keyframes-at-cuts",
            "-o", temp_path,
            "--force-overwrites",
            "--no-warnings",
            clip_info["url"],
        ]

        result = subprocess.run(cmd_download, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"    yt-dlp error: {result.stderr[:200]}")
            # Fallback: download full video, then extract with ffmpeg
            return download_clip_fallback(clip_info, output_dir)

        if not os.path.exists(temp_path):
            print(f"    ⚠ yt-dlp didn't create output, trying fallback...")
            return download_clip_fallback(clip_info, output_dir)

        # Step 2: Re-encode to exactly 25fps, no audio, 4 seconds max
        cmd_reencode = [
            "ffmpeg", "-y",
            "-i", temp_path,
            "-t", str(duration),
            "-r", "25",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-an",      # No audio (visual-only model)
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        subprocess.run(cmd_reencode, capture_output=True, check=True)

        # Clean up temp
        if os.path.exists(temp_path):
            os.remove(temp_path)

        size_kb = os.path.getsize(output_path) / 1024
        print(f"  ✓ Done ({size_kb:.0f} KB): {clip_info['name']}.mp4")
        return output_path

    except Exception as e:
        print(f"  ✗ Error: {e}")
        for f in [temp_path, output_path]:
            if os.path.exists(f):
                os.remove(f)
        return download_clip_fallback(clip_info, output_dir)


def download_clip_fallback(clip_info, output_dir):
    """Fallback: download full video, extract segment with ffmpeg, delete full video."""
    output_path = os.path.join(output_dir, f"{clip_info['name']}.mp4")
    full_path = os.path.join(output_dir, f"_full_{clip_info['name']}.mp4")
    start = clip_info["start"]
    duration = clip_info["duration"]

    print(f"    Using fallback (download + extract)...")

    try:
        # Download full video at low resolution
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "-f", "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", full_path,
            "--force-overwrites",
            "--no-warnings",
            clip_info["url"],
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        # Extract just the 4-second clip at 25fps
        cmd_extract = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", full_path,
            "-t", str(duration),
            "-r", "25",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-an",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        subprocess.run(cmd_extract, capture_output=True, check=True)

        # Delete the full video immediately
        if os.path.exists(full_path):
            os.remove(full_path)

        size_kb = os.path.getsize(output_path) / 1024
        print(f"  ✓ Done via fallback ({size_kb:.0f} KB): {clip_info['name']}.mp4")
        return output_path

    except Exception as e:
        print(f"  ✗ Fallback failed: {e}")
        for f in [full_path, output_path]:
            if os.path.exists(f):
                os.remove(f)
        return None


def create_manifest(output_dir, results):
    """Create manifest.json with clip metadata."""
    manifest = []
    for clip_info, path in results:
        if path and os.path.exists(path):
            manifest.append({
                "filename": f"{clip_info['name']}.mp4",
                "name": clip_info["name"].replace("_", " ").title(),
                "description": clip_info["description"],
                "source": clip_info["source"],
                "duration": clip_info["duration"],
            })

    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n  ✓ Manifest saved ({len(manifest)} clips)")


def main():
    print("=" * 60)
    print("  Downloading 4-Second TED Talk Clips for Lip Reading Demo")
    print("=" * 60)

    check_dependencies()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Clean up any oversized files from previous runs
    if os.path.isdir(OUTPUT_DIR):
        for fname in os.listdir(OUTPUT_DIR):
            fpath = os.path.join(OUTPUT_DIR, fname)
            if fname.endswith(".mp4") and os.path.getsize(fpath) > 5 * 1024 * 1024:
                print(f"  🗑️ Removing oversized file: {fname}")
                os.remove(fpath)

    results = []
    for clip in SAMPLE_CLIPS:
        path = download_clip(clip, OUTPUT_DIR)
        results.append((clip, path))

    create_manifest(OUTPUT_DIR, results)

    success_count = sum(1 for _, p in results if p is not None)
    print(f"\n{'=' * 60}")
    print(f"  ✓ Downloaded {success_count}/{len(SAMPLE_CLIPS)} clips (4s each)")
    print(f"  📁 Saved to: {OUTPUT_DIR}")
    print(f"\n  Next: python app.py → click 'Sample Videos'")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
