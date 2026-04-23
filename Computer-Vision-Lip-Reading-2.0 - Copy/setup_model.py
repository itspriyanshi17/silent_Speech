"""
Setup script for downloading Auto-AVSR pretrained model weights.
Run this once before starting the app:
    python setup_model.py
"""

import os
import subprocess
import sys
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── Chaplin repo (contains the inference pipeline) ───
CHAPLIN_DIR = os.path.join(SCRIPT_DIR, "chaplin")

# ─── Model weight URLs (from HuggingFace, hosted by Chaplin author) ───
MODEL_FILES = {
    "benchmarks/LRS3/models/LRS3_V_WER19.1/model.pth":
        "https://huggingface.co/Amanvir/LRS3_V_WER19.1/resolve/main/model.pth",
    "benchmarks/LRS3/models/LRS3_V_WER19.1/model.json":
        "https://huggingface.co/Amanvir/LRS3_V_WER19.1/resolve/main/model.json",
    "benchmarks/LRS3/language_models/lm_en_subword/model.pth":
        "https://huggingface.co/Amanvir/lm_en_subword/resolve/main/model.pth",
    "benchmarks/LRS3/language_models/lm_en_subword/model.json":
        "https://huggingface.co/Amanvir/lm_en_subword/resolve/main/model.json",
}


def download_file(url, dest_path):
    """Download a file with progress reporting."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.exists(dest_path):
        size_mb = os.path.getsize(dest_path) / (1024 * 1024)
        print(f"  ✓ Already exists ({size_mb:.1f} MB): {os.path.basename(dest_path)}")
        return

    print(f"  ⬇ Downloading: {os.path.basename(dest_path)}...")
    try:
        urllib.request.urlretrieve(url, dest_path)
        size_mb = os.path.getsize(dest_path) / (1024 * 1024)
        print(f"  ✓ Done ({size_mb:.1f} MB)")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise


def clone_chaplin():
    """Clone the Chaplin repo (contains auto_avsr inference pipeline)."""
    if os.path.exists(os.path.join(CHAPLIN_DIR, "pipelines", "pipeline.py")):
        print("✓ Chaplin repo already cloned.")
        return

    print("⬇ Cloning Chaplin repository (contains Auto-AVSR pipeline)...")
    subprocess.run(
        ["git", "clone", "--depth", "1", "https://github.com/amanvirparhar/chaplin.git", CHAPLIN_DIR],
        check=True,
    )
    print("✓ Chaplin repo cloned successfully.")


def download_models():
    """Download pretrained model weights from HuggingFace."""
    print("\n⬇ Downloading pretrained model weights...")
    for rel_path, url in MODEL_FILES.items():
        dest = os.path.join(CHAPLIN_DIR, rel_path)
        download_file(url, dest)
    print("✓ All model weights downloaded.")


def install_dependencies():
    """Install required Python packages."""
    print("\n⬇ Installing Python dependencies...")
    packages = [
        "torch", "torchvision", "torchaudio",
        "mediapipe", "opencv-python", "flask",
        "scipy", "scikit-image", "av", "six",
        "sentencepiece", "numpy",
    ]
    subprocess.run(
        [sys.executable, "-m", "pip", "install"] + packages,
        check=True,
    )
    print("✓ Dependencies installed.")


def main():
    print("=" * 60)
    print("  Auto-AVSR Lip Reading Model Setup")
    print("  (State-of-the-art: 19.1% WER on LRS3)")
    print("=" * 60)

    clone_chaplin()
    download_models()

    print("\n" + "=" * 60)
    print("  ✓ Setup complete!")
    print("  Run: python app.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
