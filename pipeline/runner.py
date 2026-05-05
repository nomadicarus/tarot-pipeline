import logging
import pathlib

from pipeline import compositor

logger = logging.getLogger(__name__)


def run(generate, composite, deck, **kwargs):
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

        s, sk, f = compositor.composite_batch(
            raw_dir=raw_dir,
            output_dir=out_dir,
            svg_path=kwargs.get("template"),
            **kwargs,
        )

        logger.info(f" ✓ {s} composited  ↷ {sk} skipped  ✗ {f} failed")
