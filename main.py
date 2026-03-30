"""
AI Songwriting System – Main Entry Point
=========================================
Runs the full pipeline end-to-end in the correct order, then launches the UI.

Usage:
    python main.py [--step STEP] [--ui-only]

Options:
    --step    Run a specific step only: dataset | label | index | ui
    --ui-only Skip pipeline, launch UI directly
    --help    Show this message
"""

import argparse
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent

STEPS = {
    "dataset": ROOT / "scripts" / "01_build_dataset.py",
    "label":   ROOT / "scripts" / "02_label_songs.py",
    "index":   ROOT / "scripts" / "03_build_index.py",
}


def run_script(path: Path):
    print(f"\n{'='*60}")
    print(f"  Running: {path.name}")
    print(f"{'='*60}")
    result = subprocess.run([sys.executable, str(path)], check=False)
    if result.returncode != 0:
        print(f"\n[ERROR] {path.name} exited with code {result.returncode}")
        sys.exit(result.returncode)


def launch_ui():
    print("\n" + "="*60)
    print("  Launching Streamlit UI …")
    print("="*60)
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "frontend" / "app.py")],
        check=False,
    )


def main():
    parser = argparse.ArgumentParser(description="AI Songwriting System")
    parser.add_argument(
        "--step",
        choices=["dataset", "label", "index", "ui"],
        help="Run a single step only",
    )
    parser.add_argument(
        "--ui-only",
        action="store_true",
        help="Skip pipeline steps, launch UI directly",
    )
    args = parser.parse_args()

    if args.ui_only:
        launch_ui()
        return

    if args.step:
        if args.step == "ui":
            launch_ui()
        else:
            run_script(STEPS[args.step])
        return

    # Full pipeline
    for step_name, script_path in STEPS.items():
        run_script(script_path)

    launch_ui()


if __name__ == "__main__":
    main()
