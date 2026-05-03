import logging
import pathlib

logger = logging.getLogger(__name__)


def run(generate=False, composite=False, **kwargs):
    deck_id = kwargs.get("deck")
    base_path = pathlib.Path("output")

    raw_dir = base_path / deck_id / "raw" if deck_id else base_path / "raw"
    comp_dir = (
        base_path / deck_id / "composited" if deck_id else base_path / "composited"
    )

    if generate:
        logger.info(f"Generation logic triggered for {deck_id}")

    if composite:
        from pipeline.compositor import composite_batch

        logger.info(f"── Compositing Deck: {deck_id if deck_id else 'Default'} ──")

        # Consolidate shadow parameters
        shadow_params = {
            "add_shadow": kwargs.get("add_shadow", True),
            "shadow_radius": int(kwargs.get("shadow_radius", 5)),
            "shadow_offset": (
                int(kwargs.get("shadow_offset_x", 3)),
                int(kwargs.get("shadow_offset_y", 3)),
            ),
        }

        s, sk, f = composite_batch(
            raw_dir=raw_dir,
            output_dir=comp_dir,
            svg_path=kwargs.get("template"),
            width=int(kwargs.get("width", 734)),
            height=int(kwargs.get("height", 1024)),
            pad_edge=kwargs.get("pad_edge"),  # compositor handles None
            pad_internal=int(kwargs.get("pad_internal", 30)),
            force=kwargs.get("force", False),
            **shadow_params,
        )
        logger.info(f" ✓ {s} composited  ↷ {sk} skipped  ✗ {f} failed")
