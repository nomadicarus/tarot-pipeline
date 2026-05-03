"""
pipeline/runner.py — orchestrates generation and compositing stages.

Called by main.py. Loads config from JSON directly (no config.cards /
config.decks Python modules — those don't exist; config is JSON files).

Stages:
    generate  — calls generator.generate_batch() per deck
    composite — calls compositor.composite_batch() per deck

Both stages are independently runnable via CLI flags.
Default (no flags): generate only.
"""

import json
import logging
import pathlib
import sys

logger = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

CARDS_JSON = ROOT / "config" / "cards.json"
DECKS_JSON = ROOT / "config" / "decks.json"
SVG_FRAME  = ROOT / "assets" / "cardface.svg"


# ── config loaders ────────────────────────────────────────────────────────

def _load_decks(deck_id: str = None) -> list:
    """Load all decks from decks.json, optionally filtered to one deck."""
    decks = json.loads(DECKS_JSON.read_text())["decks"]
    if deck_id:
        decks = [d for d in decks if d["id"] == deck_id]
        if not decks:
            raise ValueError(
                f"Deck '{deck_id}' not found. "
                f"Available: {[d['id'] for d in json.loads(DECKS_JSON.read_text())['decks']]}"
            )
    return decks


def _load_cards(card_names: list = None) -> list:
    """Load all 78 cards from cards.json, optionally filtered by name."""
    data  = json.loads(CARDS_JSON.read_text())
    cards = list(data["major_arcana"])
    for suit_cards in data["minor_arcana"].values():
        cards.extend(suit_cards)
    if card_names:
        names_lower = [n.lower() for n in card_names]
        cards = [c for c in cards if c["name"].lower() in names_lower]
    return cards


# ── raw directory validation ──────────────────────────────────────────────

def validate_raw_directory(raw_dir: pathlib.Path) -> list:
    """
    Check all PNGs in raw_dir for iTXt metadata.
    Returns list of (filename, issue) tuples for files with problems.
    Supports PNG, JPG, JPEG, TIFF, WEBP — reads metadata from PNG files only
    (iTXt is a PNG-specific format; other formats will report missing metadata).
    """
    from pipeline.manifest import read_metadata

    raw_dir = pathlib.Path(raw_dir)
    issues  = []

    for ext in ("*.png", "*.jpg", "*.jpeg", "*.tiff", "*.webp"):
        for f in raw_dir.glob(ext):
            if f.suffix.lower() != ".png":
                issues.append((f.name, "non-PNG format — iTXt metadata not supported"))
                continue
            meta = read_metadata(f)
            if not meta:
                issues.append((f.name, "missing iTXt metadata"))

    return issues


# ── main run function ─────────────────────────────────────────────────────

def run(
    generate:    bool  = False,
    composite:   bool  = False,
    deck:        str   = None,
    cards:       list  = None,
    force:       bool  = False,
    no_metadata: bool  = False,
    guardrail:   str   = None,
    deck_type:   str   = "tarot",
):
    """
    Orchestrate generation and/or compositing.

    Args:
        generate:    Run image generation stage.
        composite:   Run compositing stage.
        deck:        Single deck ID to process (None = all decks).
        cards:       List of card names to process (None = all cards).
        force:       Re-generate/re-composite existing files.
        no_metadata: Skip writing iTXt metadata into generated PNGs.
        guardrail:   Override guardrail mode ("preflight"|"realtime"|"off").
        deck_type:   Deck type written to image metadata (default "tarot").
    """
    if not generate and not composite:
        raise ValueError(
            "Nothing to do — pass --generate and/or --composite."
        )

    decks      = _load_decks(deck)
    all_cards  = _load_cards(cards)

    # ── GENERATION ────────────────────────────────────────────────────────

    if generate:
        from pipeline.generator import generate_batch

        logger.info("=== GENERATION STAGE ===")

        for d in decks:
            generate_batch(
                cards       = all_cards,
                deck        = d,
                output_root = str(ROOT / "output"),
                force       = force,
                no_metadata = no_metadata,
                guardrail   = guardrail,
                deck_type   = deck_type,
            )

    # ── COMPOSITING ───────────────────────────────────────────────────────

    if composite:
        from pipeline.compositor import composite_batch

        logger.info("=== COMPOSITING STAGE ===")

        for d in decks:
            raw_dir    = ROOT / "output" / d["id"] / "raw"
            output_dir = ROOT / "output" / d["id"]

            if not raw_dir.exists():
                logger.warning(
                    f"No /raw folder for deck '{d['id']}' — skipping composite."
                )
                continue

            # Validate raw directory before compositing
            issues = validate_raw_directory(raw_dir)
            if issues:
                logger.warning(f"{len(issues)} file(s) with metadata issues in {raw_dir}:")
                for name, issue in issues[:10]:
                    logger.warning(f"  {name}: {issue}")

            card_names = [c["name"] for c in all_cards] if cards else None

            print(f"\n── Compositing: {d['name']} ──")
            succeeded, skipped, failed = composite_batch(
                raw_dir    = raw_dir,
                output_dir = output_dir,
                svg_path   = SVG_FRAME,
                deck_id    = d["id"],
                card_names = card_names,
                force      = force,
            )
            print(
                f"   ✓ {succeeded} composited  "
                f"↷ {skipped} skipped  "
                f"✗ {failed} failed"
            )
