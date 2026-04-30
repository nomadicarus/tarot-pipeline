"""
compositor.py — composites generated art onto the card frame SVG.

Layout:
  - Card frame: 734 × 1024px (SVG viewBox)
  - Art is scaled to fill the full card area and placed behind the frame
  - Frame (with multiply shading gradient) is composited on top
  - Drop shadow applied: multiply blend, 2px radius, 2px offset (bottom-right, 315°)

Output: final composited PNG per card, ready for print or display.
"""

import base64
import io
import logging
import pathlib
import re
from functools import lru_cache

import numpy as np
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — derived from SVG analysis
# ---------------------------------------------------------------------------

CARD_W = 734
CARD_H = 1024
PAD_ART_W = 124
PAD_ART_H = 130


# Drop shadow settings (locked in — multiply blend, bottom-right)
SHADOW_RADIUS = 2
SHADOW_OFFSET_X = 2
SHADOW_OFFSET_Y = 2
SHADOW_COLOR = (0, 0, 0)


# ---------------------------------------------------------------------------
# Card frame loading (cached — only parsed once per run)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_card_frame(svg_path: str) -> Image.Image:
    """
    Load the card frame SVG and extract the embedded PNG.
    Returns an RGBA Image at CARD_W × CARD_H.
    Cached so the SVG is only parsed once per pipeline run.
    """
    svg_text = pathlib.Path(svg_path).read_text()

    # Extract base64-encoded embedded PNG
    match = re.search(r'data:image/png;base64,([^"\']+)', svg_text)
    if not match:
        raise ValueError(f"No embedded PNG found in SVG: {svg_path}")

    png_bytes = base64.b64decode(match.group(1))
    frame = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    # Resize to canonical card dimensions if needed
    if frame.size != (CARD_W, CARD_H):
        frame = frame.resize((CARD_W, CARD_H), Image.LANCZOS)

    logger.debug(f"Card frame loaded: {frame.size}")
    return frame


# ---------------------------------------------------------------------------
# Drop shadow
# ---------------------------------------------------------------------------


def apply_drop_shadow(
    card_img: Image.Image,
    radius: int = SHADOW_RADIUS,
    offset_x: int = SHADOW_OFFSET_X,
    offset_y: int = SHADOW_OFFSET_Y,
    shadow_color: tuple = SHADOW_COLOR,
) -> Image.Image:
    """
    Apply a multiply-blend drop shadow to a card image (RGBA).

    Returns a new RGBA image expanded by the shadow padding.
    The output is placed on a transparent background so it can be
    composited freely by the caller.
    """
    pad = radius * 3 + max(abs(offset_x), abs(offset_y)) + 4
    W, H = card_img.size
    canvas_w = W + pad * 2
    canvas_h = H + pad * 2

    # Build blurred shadow alpha from the card's own alpha channel
    card_alpha = card_img.split()[3]
    shadow_canvas = Image.new("L", (canvas_w, canvas_h), 0)
    shadow_canvas.paste(card_alpha, (pad + offset_x, pad + offset_y))
    shadow_blurred = shadow_canvas.filter(ImageFilter.GaussianBlur(radius))

    # Build shadow RGBA layer
    # shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), shadow_color + (0,))
    # shadow_layer.putalpha(shadow_blurred)
    shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), shadow_color + (0,))
    shadow_layer.putalpha(shadow_blurred)

    # Multiply shadow onto a white background then alpha-composite card on top
    # white_bg = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 0))
    white_bg = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))

    # bg_arr = np.array(white_bg).astype(float)
    # shadow_arr = np.array(shadow_layer).astype(float)
    bg_arr = np.array(white_bg).astype(float)
    shadow_arr = np.array(shadow_layer).astype(float)

    # shadow_a = shadow_arr[:, :, 3:4] / 255.0
    # mult_rgb = bg_arr[:, :, :3] * shadow_arr[:, :, :3] / 255.0
    # blended = bg_arr[:, :, :3] * (1 - shadow_a) + mult_rgb * shadow_a
    # bg_arr[:, :, 3] = shadow_arr[:, :, 3]
    shadow_a = shadow_arr[:, :, 3:4] / 255.0
    mult_rgb = bg_arr[:, :, :3] * shadow_arr[:, :, :3] / 255.0
    blended = bg_arr[:, :, :3] * (1 - shadow_a) + mult_rgb * shadow_a
    bg_arr[:, :, :3] = blended

    # base = Image.fromarray(bg_arr.astype(np.uint8))
    base = shadow_layer
    base = Image.fromarray(bg_arr.astype(np.uint8))

    # Place the card on the canvas
    # card_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    # card_canvas.paste(card_img, (pad, pad))
    card_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    card_canvas.paste(card_img, (pad, pad))

    # result = Image.alpha_composite(base.convert("RGBA"), card_canvas)
    # Composite: Card on top of Shadow
    return Image.alpha_composite(base, card_canvas)
    # return result
    result = Image.alpha_composite(base.convert("RGBA"), card_canvas)
    return result


# ---------------------------------------------------------------------------
# Main composite function
# ---------------------------------------------------------------------------


def composite_card(
    art_path: pathlib.Path,
    svg_path: pathlib.Path,
    output_path: pathlib.Path,
    add_shadow: bool = True,
) -> bool:
    """
    Composite generated art + card frame → final card PNG.

    Steps:
      1. Load generated art, resize to card dimensions
      2. Place art as background layer
      3. Composite card frame (with shading gradient) on top
      4. Optionally apply drop shadow
      5. Save final PNG

    Args:
        art_path:    Path to raw generated art PNG from Gemini.
        svg_path:    Path to the card frame SVG.
        output_path: Where to save the final composited card.
        add_shadow:  Whether to add the drop shadow (default True).

    Returns:
        True on success, False on error.
    """
    try:
        art_path = pathlib.Path(art_path)
        svg_path = pathlib.Path(svg_path)
        output_path = pathlib.Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Load and resize art to fill card dimensions
        cw = CARD_W - PAD_ART_W
        ch = CARD_H - PAD_ART_H
        w2 = PAD_ART_W / 2
        h2 = PAD_ART_H / 2
        art = Image.open(art_path).convert("RGBA")
        art_r1 = art.resize((cw, ch), Image.LANCZOS)
        art_resized = Image.new("RGBA", (CARD_W, CARD_H), (255, 255, 255, 0))
        art_resized.paste(art_r1, (int(w2), int(h2)))
        art_resized = art.resize((CARD_W, CARD_H), Image.LANCZOS)

        # 2. Load the card frame (cached)
        frame = load_card_frame(str(svg_path))

        # # 3. Composite: art behind, frame on top
        # composite = Image.alpha_composite(art_resized, frame)

        # 3. Composite: frame behidn, art on top
        # composite = Image.alpha_composite(frame, art_resized)
        composite = Image.alpha_composite(frame, art_resized)
        # 3. Composite: art behind, frame on top
        composite = Image.alpha_composite(art_resized, frame)

        # 4. Drop shadow
        if add_shadow:
            composite = apply_drop_shadow(composite)

        # 5. Save
        # Convert to RGB for final PNG (white background for any remaining alpha)
        final = Image.new("RGBA", composite.size, (255, 255, 255, 0))
        final = Image.new("RGB", composite.size, (255, 255, 255))
        final.paste(composite, mask=composite.split()[3])
        final.save(output_path, "PNG", optimize=True)

        logger.info(f"Composited: {output_path.name}")
        return True

    except Exception as e:
        logger.error(f"Compositing failed for {art_path.name}: {e}")
        return False


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

    root = pathlib.Path(__file__).parent.parent
    svg = root / "assets" / "cardface.svg"

    # Use a solid colour test image as stand-in for generated art
    test_art = root / "output" / "test_art.png"
    placeholder = Image.new("RGB", (600, 900), color=(72, 40, 120))
    placeholder.save(test_art)

    out = root / "output" / "test_composite.png"
    success = composite_card(test_art, svg, out)
    print(f"Composite test: {'passed ✓' if success else 'FAILED ✗'}")
    print(f"Output: {out}")
