"""
pipeline/compositor.py — card compositing stage.
"""

import base64
import io
import json
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

# ─────────────────────────────────────────────────────────────────
# ★  SIZING & PADDING VARIABLES  ★
# ─────────────────────────────────────────────────────────────────

CARD_W = 734  # card frame canvas width (px)
CARD_H = 1024  # card frame canvas height (px)

PAD_ART_W = 45  # horizontal padding inside frame
PAD_ART_H = 45  # vertical padding inside frame

ART_W = CARD_W - (PAD_ART_W)
ART_H = CARD_H - (PAD_ART_H)

ART_OFFSET_X = PAD_ART_W
ART_OFFSET_Y = PAD_ART_H

# ─────────────────────────────────────────────────────────────────
# ★  DROP SHADOW SETTINGS  ★
# ─────────────────────────────────────────────────────────────────

SHADOW_RADIUS = 2
SHADOW_OFFSET_X = 2
SHADOW_OFFSET_Y = 2
SHADOW_COLOR = (0, 0, 0)

# ── HELPERS ──────────────────────────────────────────────────────────────


def _scan_raw(raw_dir):
    SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    return [
        p
        for p in raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    ]


def _infer_name(path):
    return path.stem.replace("_", " ").replace("-", " ").strip().lower()


def _load_mapping(mapping_path):
    if not mapping_path:
        return {}
    try:
        path = pathlib.Path(mapping_path)
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Mapping load failed: {e}")
        return {}


@lru_cache(maxsize=1)
def _load_frame(svg_path: str) -> Image.Image:
    """Extract embedded PNG from SVG and cache it."""
    svg_text = pathlib.Path(svg_path).read_text()
    match = re.search(r'data:image/png;base64,([^"\']+)', svg_text)
    if not match:
        raise ValueError(f"No embedded PNG found in SVG: {svg_path}")
    frame = Image.open(io.BytesIO(base64.b64decode(match.group(1)))).convert("RGBA")
    if frame.size != (CARD_W, CARD_H):
        frame = frame.resize((CARD_W, CARD_H), Image.LANCZOS)
    return frame


def _apply_shadow(img: Image.Image) -> Image.Image:
    """Applies drop shadow while preserving transparency."""
    pad = SHADOW_RADIUS * 3 + max(abs(SHADOW_OFFSET_X), abs(SHADOW_OFFSET_Y)) + 4
    W, H = img.size
    cw, ch = W + pad * 2, H + pad * 2

    # Create shadow mask from original alpha
    shadow_mask = Image.new("L", (cw, ch), 0)
    shadow_mask.paste(img.split()[3], (pad + SHADOW_OFFSET_X, pad + SHADOW_OFFSET_Y))
    shadow_blur = shadow_mask.filter(ImageFilter.GaussianBlur(SHADOW_RADIUS))

    # Shadow layer
    shadow_layer = Image.new("RGBA", (cw, ch), SHADOW_COLOR + (0,))
    shadow_layer.putalpha(shadow_blur)

    # Composite on transparent base
    base_canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    final_canvas = Image.alpha_composite(base_canvas, shadow_layer)

    # Place card on top
    card_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    card_layer.paste(img, (pad, pad))

    return Image.alpha_composite(final_canvas, card_layer)


# ── PUBLIC API ───────────────────────────────────────────────────────────


def composite_card(raw_path, svg_path, output_path, add_shadow=True):
    """Composites art with frame using the frame as an alpha mask."""
    try:
        output_path = pathlib.Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Load assets
        frame = _load_frame(str(svg_path))
        art = Image.open(raw_path).convert("RGBA")

        # 2. Use frame alpha as clipping mask for the art
        frame_mask = frame.split()[3]
        art_mask = frame_mask.resize((ART_W, ART_H), Image.LANCZOS)

        # 3. Resize and clip art
        art_resized = art.resize((ART_W, ART_H), Image.LANCZOS)
        art_final = Image.new("RGBA", (ART_W, ART_H), (0, 0, 0, 0))
        art_final.paste(art_resized, (0, 0), mask=art_mask)

        # 4. Composite Layers
        canvas = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
        canvas.alpha_composite(frame)
        canvas.alpha_composite(art_final, dest=(ART_OFFSET_X, ART_OFFSET_Y))

        # 5. Add Shadow
        if add_shadow:
            canvas = _apply_shadow(canvas)

        canvas.save(output_path, "PNG", optimize=True)
        logger.info(f"Composited: {output_path.name}")
        return True

    except Exception as e:
        logger.error(f"Composite failed for {raw_path.name}: {e}")
        return False


def composite_batch(
    raw_dir,
    output_dir,
    svg_path,
    deck_id=None,
    deck_type=None,
    arcana=None,
    suit=None,
    card_names=None,
    force=False,
    add_shadow=True,
    mapping_path=None,
    force_raw=False,
    preview=False,
):
    """Processes multiple cards with metadata filtering or raw bypass."""
    from pipeline.manifest import read_metadata

    raw_dir, output_dir = pathlib.Path(raw_dir), pathlib.Path(output_dir)
    mapping = _load_mapping(mapping_path)
    raw_candidates = _scan_raw(raw_dir)
    selected = []

    for path in raw_candidates:
        # --- 1. FORCE RAW PATHWAY ---
        if force_raw:
            selected.append(path)
            if preview:
                logger.info(f"[FORCE] {path.name} -> Added (bypass)")
            continue

        # --- 2. GOVERNANCE PATHWAY ---
        source, meta = "filename", {}
        if path.name in mapping:
            meta, source = mapping[path.name], "mapping"
        else:
            meta = read_metadata(path)
            if meta and meta.get("card_name"):
                source = "metadata"

        name = (meta.get("card_name") or _infer_name(path)).lower()
        matched, reason = True, ""

        if card_names and name not in [c.lower() for c in card_names]:
            matched, reason = False, f"name '{name}' not in filter"
        if matched and deck_id and meta.get("deck_id") != deck_id:
            matched, reason = False, f"deck mismatch: {meta.get('deck_id')}"

        if preview:
            status = "MATCH" if matched else "SKIP"
            logger.info(f"[{status}] {path.name} -> {name} ({source}) {reason}")
        if matched:
            selected.append(path)

    if preview or not selected:
        return len(selected), 0, 0

    succeeded = skipped = failed = 0
    for raw_path in selected:
        out_path = output_dir / f"{raw_path.stem}.png"
        if out_path.exists() and not force:
            skipped += 1
            continue
        if composite_card(raw_path, svg_path, out_path, add_shadow):
            succeeded += 1
        else:
            failed += 1

    return succeeded, skipped, failed
