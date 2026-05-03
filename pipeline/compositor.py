# pipeline/compositor.py (refactored for runner compatibility)

"""
compositor.py — card compositing stage only.

Reads raw PNGs from output/{deck}/raw/, filters by iTXt metadata,
composites each with the card frame SVG, applies drop shadow, saves
final PNGs to output/{deck}/.

Can be run independently of generation — raw images are self-describing
via iTXt metadata so no cards.json lookup is needed at composite time.

CLI (via main.py):
    python main.py --composite                          # all raw in all decks
    python main.py --composite --deck thoth             # one deck, all cards
    python main.py --composite --deck thoth --suit wands
    python main.py --composite --deck thoth --arcana major
    python main.py --composite --deck thoth --card "The Fool"
    python main.py --composite --deck thoth --card "The Fool" "The Magus"

Drop shadow (locked per governance):
    blend mode : multiply
    radius     : 2px
    offset     : 2px bottom-right (315 degrees)

Z-order (locked per governance):
    layer 0 : frame
    layer 1 : art (generated image)
    layer 2 : top text overlay (future)
    layer 3 : bottom text overlay (future)

Padding / sizing variables — adjust these to reposition art within frame:
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

from pipeline.manifest import filter_raw, read_metadata

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
logger = logging.getLogger(__name__)
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ─────────────────────────────────────────────────────────────────
# ★  SIZING & PADDING VARIABLES — adjust here  ★
# ─────────────────────────────────────────────────────────────────

CARD_W = 734  # card frame canvas width (px)
CARD_H = 1024  # card frame canvas height (px)

PAD_ART_W = 30  # horizontal padding inside frame (px each side)
PAD_ART_H = 30  # vertical padding inside frame (px each side)

# Art area derived from padding — do not edit directly
ART_W = CARD_W - (PAD_ART_W * 2)
ART_H = CARD_H - (PAD_ART_H * 2)
ART_OFFSET_X = PAD_ART_W
ART_OFFSET_Y = PAD_ART_H
SHADOW_RADIUS = 2  # blur radius (px)
SHADOW_OFFSET_X = 2  # x offset (px) — positive = right
SHADOW_OFFSET_Y = 2  # y offset (px) — positive = down
SHADOW_COLOR = (0, 0, 0)

# ── card frame loading ────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def load_card_frame(svg_path: str) -> Image.Image:
    """
    Load card frame from SVG (extracts embedded PNG).
    Cached — parsed once per run.
    """
    svg_text = pathlib.Path(svg_path).read_text()
    match = re.search(r'data:image/png;base64,([^"\']+)', svg_text)
    if not match:
        raise ValueError(f"No embedded PNG found in SVG: {svg_path}")

    frame = Image.open(io.BytesIO(base64.b64decode(match.group(1)))).convert("RGBA")
    if frame.size != (CARD_W, CARD_H):
        frame = frame.resize((CARD_W, CARD_H), Image.LANCZOS)
    return frame


# ── drop shadow ───────────────────────────────────────────────────────────


def apply_drop_shadow(card_img: Image.Image) -> Image.Image:
    """
    Apply multiply-blend drop shadow (locked settings per governance).
    Returns expanded RGBA image with shadow on transparent background.
    """
    pad = SHADOW_RADIUS * 3 + max(abs(SHADOW_OFFSET_X), abs(SHADOW_OFFSET_Y)) + 4
    W, H = card_img.size
    canvas_w = W + pad * 2
    canvas_h = H + pad * 2

    # Build blurred shadow from card alpha
    shadow_canvas = Image.new("L", (canvas_w, canvas_h), 0)
    shadow_canvas.paste(
        card_img.split()[3], (pad + SHADOW_OFFSET_X, pad + SHADOW_OFFSET_Y)
    )
    shadow_blurred = shadow_canvas.filter(ImageFilter.GaussianBlur(SHADOW_RADIUS))

    shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), SHADOW_COLOR + (0,))
    shadow_layer.putalpha(shadow_blurred)

    # Multiply shadow onto white base
    white_bg = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
    bg_arr = np.array(white_bg).astype(float)
    shadow_arr = np.array(shadow_layer).astype(float)
    shadow_a = shadow_arr[:, :, 3:4] / 255.0
    mult_rgb = bg_arr[:, :, :3] * shadow_arr[:, :, :3] / 255.0
    blended = bg_arr[:, :, :3] * (1 - shadow_a) + mult_rgb * shadow_a
    bg_arr[:, :, :3] = blended
    base = Image.fromarray(bg_arr.astype(np.uint8))

    # Place card on canvas — transparent background preserved
    card_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    card_canvas.paste(card_img, (pad, pad))
    return Image.alpha_composite(base.convert("RGBA"), card_canvas)


# ── single card composite ─────────────────────────────────────────────────


def composite_card(
    raw_path: pathlib.Path,
    svg_path: pathlib.Path,
    output_path: pathlib.Path,
    add_shadow: bool = True,
) -> bool:
    """
    Composite a single raw PNG with the card frame.

    Z-order (per governance):
        layer 0 : frame  (bottom)
        layer 1 : art    (generated image, on top of frame)
        layer 2 : top text overlay    (future)
        layer 3 : bottom text overlay (future)

    Args:
        raw_path:    Path to raw generated art PNG.
        svg_path:    Path to card frame SVG.
        output_path: Where to save the final composited card.
        add_shadow:  Apply drop shadow (default True).

    Returns:
        True on success, False on error.
    """
    try:
        raw_path = pathlib.Path(raw_path)
        output_path = pathlib.Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Load frame (layer 0) and art (layer 1)
        frame = load_card_frame(str(svg_path))
        art = Image.open(raw_path).convert("RGBA")

        # Create canvas — frame first (layer 0)
        canvas = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
        canvas.alpha_composite(frame)

        # Resize art to fit padded art area
        art_resized = art.resize((ART_W, ART_H), Image.LANCZOS)

        # Place art on top of frame (layer 1)
        canvas.alpha_composite(art_resized, dest=(ART_OFFSET_X, ART_OFFSET_Y))

        # layer 2 / layer 3 — text overlays (future, not implemented)

        # Drop shadow
        if add_shadow:
            canvas = apply_drop_shadow(canvas)

        # Save — transparent bounding box preserved per governance
        canvas.save(output_path, "PNG", optimize=True)
        logger.info(f"Composited: {output_path.name}")
        return True

    except Exception as e:
        logger.error(f"Compositing failed for {raw_path.name}: {e}")
        return False


# ── batch composite ───────────────────────────────────────────────────────


def composite_batch(
    raw_dir: pathlib.Path,
    output_dir: pathlib.Path,
    svg_path: pathlib.Path,
    deck_id: Optional[str] = None,
    deck_type: Optional[str] = None,
    arcana: Optional[str] = None,
    suit: Optional[str] = None,
    card_name: Optional[str] = None,
    card_names: Optional[list] = None,
    force: bool = False,
    allow_unmatched: bool = True,
) -> tuple:
    """
    Composite multiple raw PNGs filtered by iTXt metadata.

    All filter args are optional AND conditions. Omit to match all.

    Args:
        raw_dir:    Path to /raw folder containing source PNGs.
        output_dir: Path to output folder for final composited PNGs.
        svg_path:   Path to card frame SVG.
        deck_id:    Filter by deck e.g. "thoth"
        deck_type:  Filter by deck type e.g. "tarot"
        arcana:     Filter by "major" or "minor"
        suit:       Filter by suit e.g. "wands"
        card_name:  Filter by single card name
        card_names: Filter by list of card names
        force:      Re-composite even if output already exists

    Returns:
        (succeeded, skipped, failed) counts
    """

    def infer_metadata_from_filename(path: pathlib.Path):
        name = path.stem

        # basic normalization
        name = name.replace("_", " ").replace("-", " ").strip()

        return {
            "card_name": name,
            "deck_id": None,
            "arcana": None,
            "suit": None,
        }

    raw_dir = pathlib.Path(raw_dir)
    output_dir = pathlib.Path(output_dir)

    # Filter raw files by metadata
    raw_files = filter_raw(
        raw_dir,
        deck_id=deck_id,
        deck_type=deck_type,
        arcana=arcana,
        suit=suit,
        card_name=card_name,
        card_names=card_names,
    )

    if not raw_files and allow_unmatched:
        logger.warning("No metadata matches — falling back to raw file scan")

        # raw_files = list(pathlib.Path(raw_dir).glob("*.png"))
        SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

        def scan_raw_files(raw_dir):
            return [
                p
                for p in raw_dir.iterdir()
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
            ]

        raw_files = scan_raw_files(raw_dir)

    for raw_path in raw_files:
        out_path = output_dir / raw_path.name

        if out_path.exists() and not force:
            logger.debug(f"Skipping (exists): {raw_path.name}")
            skipped += 1
            continue

        ok = composite_card(raw_path, svg_path, out_path)
        if ok:
            succeeded += 1
        else:
            failed += 1

    logger.info(
        f"Batch composite complete: "
        f"{succeeded} done, {skipped} skipped, {failed} failed"
    )
    return succeeded, skipped, failed


def run_composite(
    raw_dir: str,
    output_dir: str,
    svg_path: str,
    deck: str = None,
    cards: list = None,
    force: bool = False,
    allow_unmatched: bool = True,
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
