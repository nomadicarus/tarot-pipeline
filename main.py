"""
main.py — top-level entry point for the tarot card pipeline.

Stages are now independent and CLI-selectable:

    python main.py --generate                          # generate raw art only
    python main.py --composite                         # composite all /raw images
    python main.py --generate --composite              # full pipeline (generate then composite)

    # Deck filtering
    python main.py --generate --deck thoth claymation
    python main.py --composite --deck thoth

    # Card filtering
    python main.py --generate --card "The Fool" "The Magus"
    python main.py --composite --suit wands
    python main.py --composite --arcana major
    python main.py --composite --deck thoth --cards "The Fool"

    # Force regeneration/recomposite
    python main.py --generate --force
    python main.py --composite --force

    # Guardrail override
    python main.py --generate --guardrail off

Default behaviour (no flags): --generate only.

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

"""

import argparse
import logging

from pipeline.runner import run

logging.basicConfig(level=logging.INFO)


def main():
    parser = argparse.ArgumentParser(description="Tarot pipeline")

    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--composite", action="store_true")

    parser.add_argument("--deck", type=str, help="Deck ID")
    parser.add_argument("--card", nargs="*", help="Card names")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-metadata", action="store_true")
    parser.add_argument("--mapping", type=str, help="Path to metadata mapping JSON")
    parser.add_argument(
        "--force-raw",
        action="store_true",
        help="Bypass filtering and process all raw files",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Show what would be processed without running",
    )

    args = parser.parse_args()
    cards = args.card if args.card else None
    if not args.generate and not args.composite:
        args.generate = True
    run(
        generate=args.generate,
        composite=args.composite,
        deck=args.deck,
        cards=cards,
        force=args.force,
        no_metadata=args.no_metadata,
        mapping_path=args.mapping,
        force_raw=args.force_raw,
        preview=args.preview,
    )


if __name__ == "__main__":
    main()
