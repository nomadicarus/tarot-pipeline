# pipeline/runner.py

import logging
import pathlib

from pipeline.compositor import composite_batch
from pipeline.generator import generate_card_image

logger = logging.getLogger(__name__)


def run(
    generate: bool = False,
    composite: bool = False,
    deck: str = None,
    cards: list = None,
    force: bool = False,
):
    """
    Filesystem-driven pipeline runner.

    - Generator writes raw images
    - Compositor reads raw images
    - No in-memory data passing

    All stages optional and independently runnable.
    """

    if not generate and not composite:
        raise ValueError("Nothing to do: enable --generate and/or --composite")

    # ── paths ─────────────────────────────────────────────

    root = pathlib.Path("output")

    if deck:
        raw_dir = root / deck / "raw"
        output_dir = root / deck
    else:
        raw_dir = root
        output_dir = root

    svg_path = pathlib.Path("assets/cardface.svg")

    # ── GENERATION STAGE ─────────────────────────────────

    if generate:
        logger.info("=== GENERATION STAGE ===")

        # IMPORTANT:
        # You likely already have a higher-level loop for cards.
        # This runner should call THAT (not generate_card_image directly).
        #
        # If not, you’ll need to wrap your card iteration here.

        run_generation(deck=deck, cards=cards)

    # ── COMPOSITION STAGE ────────────────────────────────

    if composite:
        logger.info("=== COMPOSITION STAGE ===")

        succeeded, skipped, failed = composite_batch(
            raw_dir=raw_dir,
            output_dir=output_dir,
            svg_path=svg_path,
            deck_id=deck,
            card_names=cards,
            force=force,
        )

        logger.info(
            f"Composite results: {succeeded} ok, {skipped} skipped, {failed} failed"
        )


# ─────────────────────────────────────────────────────────
# GENERATION WRAPPER (IMPORTANT)
# ─────────────────────────────────────────────────────────


def run_generation(deck: str = None, cards: list = None):
    """
    This function should wrap your existing generation logic.

    DO NOT tightly couple it to metadata.
    Allow fallback behavior for:
      - missing metadata
      - external images
      - partial configs
    """

    from config.cards import load_cards_config  # or wherever this lives
    from config.decks import load_decks_config

    decks = load_decks_config()

    if deck:
        decks = [d for d in decks if d["id"] == deck]

    for d in decks:
        deck_id = d["id"]

        cards_config = load_cards_config(deck_id)

        if cards:
            cards_config = [c for c in cards_config if c["name"] in cards]

        for card in cards_config:
            try:
                prompt = build_prompt(card, d)  # from prompts.builder

                output_path = (
                    pathlib.Path("output") / deck_id / "raw" / f"{card['name']}.png"
                )

                generate_card_image(
                    prompt=prompt,
                    output_path=output_path,
                    card=card,
                    deck=d,
                )

            except Exception as e:
                logger.error(f"Generation failed for {card.get('name')}: {e}")
