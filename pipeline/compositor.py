# pipeline/compositor.py (refactored for runner compatibility)

import logging
import pathlib

logger = logging.getLogger(__name__)

from pipeline.compositor import composite_batch


def run_composite(
    raw_dir: str,
    output_dir: str,
    svg_path: str,
    deck: str = None,
    cards: list = None,
    force: bool = False,
):
    """Wrapper for compositing stage."""

    raw_dir = pathlib.Path(raw_dir)
    output_dir = pathlib.Path(output_dir)
    svg_path = pathlib.Path(svg_path)

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

    return succeeded, skipped, failed
