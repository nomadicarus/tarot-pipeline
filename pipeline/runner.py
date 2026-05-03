"""
runner.py — orchestrates generation and/or compositing pipeline stages.

Stages are now independent and CLI-selectable:

    python main.py --generate                          # generate raw art only
    python main.py --composite                         # composite all /raw images
    python main.py --generate --composite              # full pipeline (generate then composite)

    # Deck filtering
    python main.py --generate --decks thoth claymation
    python main.py --composite --decks thoth

    # Card filtering
    python main.py --generate --cards "The Fool" "The Magus"
    python main.py --composite --suit wands
    python main.py --composite --arcana major
    python main.py --composite --deck thoth --cards "The Fool"

    # Force regeneration/recomposite
    python main.py --generate --force
    python main.py --composite --force

    # Guardrail override
    python main.py --generate --guardrail off

Default behaviour (no flags): --generate only.
"""

import logging
import pathlib

from pipeline.compositor import infer_metadata_from_filename, run_composite
from pipeline.generator import generate_batch

logger = logging.getLogger(__name__)


def load_decks(deck_id=None):
    from config.decks import load_decks_config

    decks = load_decks_config()
    if deck_id:
        decks = [d for d in decks if d["id"] == deck_id]
    return decks


def load_cards(deck_id, card_names=None):
    from config.cards import load_cards_config

    cards = load_cards_config(deck_id)
    if card_names:
        cards = [c for c in cards if c["name"] in card_names]
    return cards


def validate_raw_directory(raw_dir):
    from pipeline.manifest import read_metadata

    raw_dir = pathlib.Path(raw_dir)
    issues = []

    # this should process all image types, or at least, PNG, JPG, JPEG, TIFF, WEBP
    for file in raw_dir.glob("*.png"):
        meta = read_metadata(file)

        if not meta:
            issues.append((file.name, "missing metadata"))
            meta = infer_metadata_from_filename(file)

    return issues


def run(
    generate=False,
    composite=False,
    deck=None,
    cards=None,
    force=False,
    no_metadata=False,
):
    if not generate and not composite:
        raise ValueError("Nothing to do")

    root = pathlib.Path("output")

    if deck:
        raw_dir = root / deck / "raw"
        output_dir = root / deck
    else:
        raw_dir = root
        output_dir = root

    svg_path = pathlib.Path("assets/cardface.svg")

    # ── GENERATION ─────────────────────────

    if generate:
        logger.info("=== GENERATION ===")

        decks = load_decks(deck)
        for d in decks:
            cards_config = load_cards(d["id"], cards)

            generate_batch(
                cards=cards_config,
                deck=d,
            )

    # ── COMPOSITION ───────────────────────

    if composite:
        logger.info("=== COMPOSITION ===")

        issues = validate_raw_directory(raw_dir)
        if issues:
            logger.warning(f"{len(issues)} files missing metadata")
            for name, issue in issues[:5]:
                logger.warning(f" - {name}: {issue}")

        run_composite(
            raw_dir=raw_dir,
            output_dir=output_dir,
            svg_path=svg_path,
            deck=deck,
            cards=cards,
            force=force,
        )
