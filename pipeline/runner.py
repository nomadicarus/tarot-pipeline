import logging
import pathlib
import sys

from pipeline import compositor

logger = logging.getLogger(__name__)


def run(generate, composite, deck, **kwargs):
    # --- generate ---
    if generate:
        if not deck:
            logger.error("No deck ID specified.")
            return

        # Import here to avoid circular imports
        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
        from pipeline.generator import generate_batch
        from config.settings import MODEL

        # Load deck config
        import json
        decks_path = pathlib.Path("config") / "decks.json"
        cards_path = pathlib.Path("config") / "cards.json"
        if not decks_path.exists() or not cards_path.exists():
            logger.error("Missing decks.json or cards.json")
            return

        decks = json.loads(decks_path.read_text())
        cards = json.loads(cards_path.read_text())

        deck_config = next((d for d in decks["decks"] if d["id"] == deck), None)
        if not deck_config:
            logger.error(f"Deck '{deck}' not found in decks.json")
            return

        # Build card list (all major + requested suit/minor cards)
        card_list = cards["major_arcana"][:]
        if "suit" in kwargs:
            suit = kwargs["suit"]
            card_list += cards["minor_arcana"].get(suit, [])

        logger.info(f"── Generating Deck: {deck} ({deck_config['name']}) ──")
        logger.info(f"   Model: {MODEL}")

        result = generate_batch(
            cards=card_list,
            deck=deck_config,
            output_root="output",
            force=kwargs.get("force", False),
            no_metadata=kwargs.get("no_metadata", False),
            guardrail=kwargs.get("guardrail"),
            deck_type="tarot",
        )

        logger.info(
            f" ✓ {result['succeeded']} generated  "
            f"↷ {result['skipped']} skipped  "
            f"✗ {result['failed']} failed"
        )
        return

    # --- composite ---
    if composite:
        if not deck:
            logger.error("No deck ID specified.")
            return

        base_path = pathlib.Path("output") / deck
        raw_dir = base_path / "raw"
        out_dir = base_path / "composited"

        if not raw_dir.exists():
            logger.error(f"Missing: {raw_dir}")
            return

        out_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"── Compositing Deck: {deck} ──")

        # Extract mask_method, pass remaining kwargs through
        mask_method = kwargs.pop("mask_method", "alpha")
        s, sk, f = compositor.composite_batch(
            raw_dir=raw_dir,
            output_dir=out_dir,
            svg_path=kwargs.get("template"),
            mask_method=mask_method,
            **kwargs,
        )

        logger.info(f" ✓ {s} composited  ↷ {sk} skipped  ✗ {f} failed")
