"""
pipeline/compositor.py — card compositing stage.

Reads raw PNGs from output/{deck}/raw/, filters by iTXt metadata,
composites each with the card frame SVG, applies drop shadow, saves
final PNGs to output/{deck}/.

Can be run independently of generation — raw images are self-describing
via iTXt metadata so no cards.json lookup is needed at composite time.

Public API:
    composite_card(raw_path, svg_path, output_path, add_shadow)
        Composite a single raw PNG with the card frame.

    composite_batch(raw_dir, output_dir, svg_path, ...)
        Composite multiple raw PNGs filtered by iTXt metadata fields.

Z-order (locked per governance):
    layer 0 : frame           ← bottom
    layer 1 : art             ← generated image, on top of frame
    layer 2 : top text        ← future
    layer 3 : bottom text     ← future

Drop shadow (locked per governance):
    multiply blend, 2px radius, 2px offset, bottom-right (315°)
"""

import base64
import io
import logging
import pathlib
import re
import sys
from functools import lru_cache
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.manifest import filter_raw

# ─────────────────────────────────────────────────────────────────
# ★  SIZING & PADDING VARIABLES — adjust here  ★
# ─────────────────────────────────────────────────────────────────

CARD_W    = 734     # card frame canvas width (px)
CARD_H    = 1024    # card frame canvas height (px)

PAD_ART_W = 30      # horizontal padding inside frame (px, each side)
PAD_ART_H = 30      # vertical padding inside frame (px, each side)

# Art area dimensions — derived from padding
ART_W        = CARD_W - (PAD_ART_W * 2)
ART_H        = CARD_H - (PAD_ART_H * 2)

# Top-left corner of art area within the canvas
ART_OFFSET_X = PAD_ART_W
ART_OFFSET_Y = PAD_ART_H

# ─────────────────────────────────────────────────────────────────
# ★  DROP SHADOW — locked per governance  ★
# ─────────────────────────────────────────────────────────────────

SHADOW_RADIUS   = 2     # blur radius (px)
SHADOW_OFFSET_X = 2     # x offset — positive = right
SHADOW_OFFSET_Y = 2     # y offset — positive = down
SHADOW_COLOR    = (0, 0, 0)


# ── frame loader ─────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_frame(svg_path: str) -> Image.Image:
    """
    Extract and return the embedded PNG from the card frame SVG.
    Cached — parsed once per run.
    """
    svg_text = pathlib.Path(svg_path).read_text()
    match    = re.search(r'data:image/png;base64,([^"\']+)', svg_text)
    if not match:
        raise ValueError(f"No embedded PNG found in SVG: {svg_path}")
    frame = Image.open(
        io.BytesIO(base64.b64decode(match.group(1)))
    ).convert("RGBA")
    if frame.size != (CARD_W, CARD_H):
        frame = frame.resize((CARD_W, CARD_H), Image.LANCZOS)
    return frame


# ── drop shadow ───────────────────────────────────────────────────────────

def _apply_shadow(img: Image.Image) -> Image.Image:
    """
    Apply multiply-blend drop shadow. Settings locked per governance.
    Returns expanded RGBA image — transparent bounding box preserved.
    """
    pad    = SHADOW_RADIUS * 3 + max(abs(SHADOW_OFFSET_X), abs(SHADOW_OFFSET_Y)) + 4
    W, H   = img.size
    cw, ch = W + pad * 2, H + pad * 2

    # Build blurred shadow from card alpha
    sc = Image.new("L", (cw, ch), 0)
    sc.paste(img.split()[3], (pad + SHADOW_OFFSET_X, pad + SHADOW_OFFSET_Y))
    sb = sc.filter(ImageFilter.GaussianBlur(SHADOW_RADIUS))

    sl = Image.new("RGBA", (cw, ch), SHADOW_COLOR + (0,))
    sl.putalpha(sb)

    # Multiply shadow onto white base
    bg  = Image.new("RGBA", (cw, ch), (255, 255, 255, 255))
    ba  = np.array(bg).astype(float)
    sa  = np.array(sl).astype(float)
    a   = sa[:, :, 3:4] / 255.0
    m   = ba[:, :, :3] * sa[:, :, :3] / 255.0
    ba[:, :, :3] = ba[:, :, :3] * (1 - a) + m * a
    base = Image.fromarray(ba.astype(np.uint8))

    # Place card on canvas — transparent bounding box preserved
    cc = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    cc.paste(img, (pad, pad))
    return Image.alpha_composite(base.convert("RGBA"), cc)


# ── single card composite ─────────────────────────────────────────────────

def composite_card(
    raw_path:    pathlib.Path,
    svg_path:    pathlib.Path,
    output_path: pathlib.Path,
    add_shadow:  bool = True,
) -> bool:
    """
    Composite a single raw PNG with the card frame SVG.

    Z-order:
        layer 0 : frame  (bottom)
        layer 1 : art    (on top of frame)
        layer 2/3: text overlays (future, not yet implemented)

    Args:
        raw_path:    Path to raw generated art PNG.
        svg_path:    Path to card frame SVG.
        output_path: Where to save the final composited card.
        add_shadow:  Apply drop shadow (default True).

    Returns:
        True on success, False on error.
    """
    try:
        output_path = pathlib.Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Load frame (layer 0) and art
        frame = _load_frame(str(svg_path))
        art   = Image.open(raw_path).convert("RGBA")

        # Start with blank canvas, composite frame first (layer 0)
        canvas = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
        canvas.alpha_composite(frame)

        # Resize art to padded art area, place on top of frame (layer 1)
        art_resized = art.resize((ART_W, ART_H), Image.LANCZOS)
        canvas.alpha_composite(art_resized, dest=(ART_OFFSET_X, ART_OFFSET_Y))

        # Layer 2 / 3 — text overlays (future)

        # Drop shadow — transparent bounding box preserved
        if add_shadow:
            canvas = _apply_shadow(canvas)

        canvas.save(output_path, "PNG", optimize=True)
        logger.info(f"Composited: {output_path.name}")
        return True

    except Exception as e:
        logger.error(f"Composite failed for {raw_path.name}: {e}")
        return False


# ── batch composite ───────────────────────────────────────────────────────

def composite_batch(
    raw_dir:    pathlib.Path,
    output_dir: pathlib.Path,
    svg_path:   pathlib.Path,
    deck_id:    Optional[str]  = None,
    deck_type:  Optional[str]  = None,
    arcana:     Optional[str]  = None,
    suit:       Optional[str]  = None,
    card_names: Optional[list] = None,
    force:      bool           = False,
    add_shadow: bool           = True,
) -> tuple:
    """
    Composite multiple raw PNGs, filtered by iTXt metadata.

    All filter args are optional AND conditions. Omit to match all.

    Args:
        raw_dir:    Path to /raw folder.
        output_dir: Path to output folder for final PNGs.
        svg_path:   Path to card frame SVG.
        deck_id:    Filter by deck e.g. "thoth"
        deck_type:  Filter by deck type e.g. "tarot"
        arcana:     Filter by "major" or "minor"
        suit:       Filter by suit e.g. "wands"
        card_names: Filter by list of card names
        force:      Re-composite even if output already exists.
        add_shadow: Apply drop shadow (default True).

    Returns:
        (succeeded, skipped, failed) counts
    """
    raw_dir    = pathlib.Path(raw_dir)
    output_dir = pathlib.Path(output_dir)

    raw_files = filter_raw(
        raw_dir,
        deck_id    = deck_id,
        deck_type  = deck_type,
        arcana     = arcana,
        suit       = suit,
        card_names = card_names,
    )

    if not raw_files:
        logger.warning(f"No raw files matched filters in {raw_dir}")
        return 0, 0, 0

    succeeded = skipped = failed = 0

    for raw_path in raw_files:
        out_path = output_dir / raw_path.name

        if out_path.exists() and not force:
            logger.debug(f"Skipping (exists): {raw_path.name}")
            skipped += 1
            continue

        ok = composite_card(raw_path, svg_path, out_path, add_shadow)
        if ok:
            succeeded += 1
        else:
            failed += 1

    logger.info(
        f"Batch composite: ✓ {succeeded}  ↷ {skipped}  ✗ {failed}"
    )
    return succeeded, skipped, failed
