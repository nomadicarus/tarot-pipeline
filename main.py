"""
main.py — top-level entry point for the tarot card pipeline.

Usage:
    # Generate all 78 cards across all 3 decks (234 images total)
    python main.py

    # Generate a specific deck only
    python main.py --decks thoth
    python main.py --decks lego_explosive claymation

    # Generate specific cards (useful for testing)
    python main.py --cards "The Fool" "The Magus" "The Priestess"

    # Force regeneration of already-completed cards
    python main.py --force

    # Combine flags
    python main.py --decks thoth --cards "The Fool" --force

    # Verbose logging
    python main.py --log-level DEBUG

Requirements:
    pip install google-genai Pillow Jinja2 python-dotenv tqdm cairosvg

Environment:
    GEMINI_API_KEY must be set in .env or as an environment variable.

Output structure:
    output/
    ├── lego_explosive/
    │   ├── raw/                  ← raw art from Gemini API
    │   ├── the_fool.png          ← final composited card
    │   └── ...
    ├── thoth/
    │   ├── raw/
    │   └── ...
    └── claymation/
        ├── raw/
        └── ...
"""

from pipeline.runner import run

if __name__ == "__main__":
    # Runner handles its own argparse — just delegate
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent))

    # Re-invoke runner's CLI
    from pipeline import runner
    import runpy
    runpy.run_module("pipeline.runner", run_name="__main__", alter_sys=True)
