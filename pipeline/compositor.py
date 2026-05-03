import base64
import io
import json
import logging
import pathlib
import re
from functools import lru_cache
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

# NOTE: Requires 'pip install cairosvg' for math-based SVG rendering
try:
    import cairosvg
except ImportError:
    cairosvg = None

logger = logging.getLogger(__name__)

# ── CONFIGURATION ──────────────────────────────────────────────────────────

PAD_INTERNAL = 100  # Margin between the frame's 'ink' edge and the start of the art
SHADOW_RADIUS = 2
SHADOW_OFFSET = (2, 2)
SHADOW_COLOR = (0, 0, 0, 180)  # Subtle black shadow

# ── HELPERS ────────────────────────────────────────────────────────────────


def _scan_raw(raw_dir: pathlib.Path):
    SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tiff"}
    return [
        p
        for p in raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    ]


def _load_mapping(mapping_path: str):
    if not mapping_path:
        return {}
    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load mapping: {e}")
        return {}


def _load_frame(svg_path: str, target_size: Tuple[int, int]) -> Image.Image:
    """
    Loads SVG. If it's a vector, it rasterizes at target_size for maximum crispness.
    If it's a wrapper, it extracts the embedded PNG.
    """
    svg_path = pathlib.Path(svg_path)
    svg_text = svg_path.read_text()

    # 1. Check for legacy Base64 Wrapper
    match = re.search(r'data:image/png;base64,([^"\']+)', svg_text)
    if match:
        return Image.open(io.BytesIO(base64.b64decode(match.group(1)))).convert("RGBA")

    # 2. Handle Pure Vector SVG
    if cairosvg is None:
        raise ImportError(
            "Vector SVG detected but 'cairosvg' is not installed. Run: pip install cairosvg"
        )

    # We render the SVG at the requested width to ensure math-based paths stay sharp
    png_data = cairosvg.svg2png(url=str(svg_path), output_width=target_size[0])
    return Image.open(io.BytesIO(png_data)).convert("RGBA")


def _get_template_metrics(
    frame: Image.Image,
    max_w: int,
    max_h: int,
    pad_edge_arg: Optional[int],
    pad_int_arg: int,
):
    """
    Calculates the geometry using the visible 'ink' of the SVG.
    """
    bbox = frame.getbbox()
    if not bbox:
        raise ValueError("Template appears to be empty.")

    # 1. Determine native 'ink' size
    native_w, native_h = frame.size
    vis_w = bbox[2] - bbox[0]
    vis_h = bbox[3] - bbox[1]

    # 2. Scale based on the VISIBLE frame fitting into the max_w/max_h
    scale = min(max_w / vis_w, max_h / vis_h)

    # 3. Apply the CLI pad_edge (gutter)
    # If pad_edge is 100, the final file will be (scaled_ink + 200)
    gutter = int((pad_edge_arg if pad_edge_arg is not None else 0) * scale)

    final_w = int(vis_w * scale) + (gutter * 2)
    final_h = int(vis_h * scale) + (gutter * 2)

    # 4. Scale the internal art padding
    scaled_pad_int = int(pad_int_arg * scale)

    return {
        "target_file_size": (final_w, final_h),
        "art_size": (
            int(vis_w * scale) - (scaled_pad_int * 2),
            int(vis_h * scale) - (scaled_pad_int * 2),
        ),
        "pad_internal": scaled_pad_int,
        "gutter": gutter,
        "crop_box": bbox,
        "scale": scale,
    }


def _apply_shadow(img: Image.Image) -> Image.Image:
    """Adds a drop shadow to the finished card."""
    pad = SHADOW_RADIUS * 4
    canvas_size = (img.width + pad * 2, img.height + pad * 2)

    # Create shadow layer
    shadow_mask = Image.new("L", canvas_size, 0)
    shadow_mask.paste(img.split()[3], (pad + SHADOW_OFFSET[0], pad + SHADOW_OFFSET[1]))
    shadow_blur = shadow_mask.filter(ImageFilter.GaussianBlur(SHADOW_RADIUS))

    shadow_layer = Image.new("RGBA", canvas_size, SHADOW_COLOR)
    shadow_layer.putalpha(shadow_blur)

    # Composite card over shadow
    final = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    final.alpha_composite(shadow_layer)
    final.paste(img, (pad, pad), mask=img)
    return final


# ── PUBLIC API ─────────────────────────────────────────────────────────────


def composite_card(
    raw_path,
    svg_path,
    output_path,
    width=734,
    height=1024,
    pad_edge=None,
    pad_internal=30,
    add_shadow=True,
):
    try:
        # Load SVG (Rendered large enough to get clean metrics)
        frame_raw = _load_frame(svg_path, (width, height))

        # Pass the 5 arguments now required by the metrics function
        m = _get_template_metrics(frame_raw, width, height, pad_edge, pad_internal)

        # Crop to ink and resize to the 'visible' portion of our target
        ink_w = m["target_file_size"][0] - (m["gutter"] * 2)
        ink_h = m["target_file_size"][1] - (m["gutter"] * 2)
        frame_ink = frame_raw.crop(m["crop_box"]).resize((ink_w, ink_h), Image.LANCZOS)

        # 1. Create the Final Canvas (includes the pad-edge/gutter)
        canvas = Image.new("RGBA", m["target_file_size"], (0, 0, 0, 0))

        # 2. Prepare the Art Mask (Derived from frame's alpha)
        full_mask = frame_ink.split()[3]
        p_int = m["pad_internal"]
        mask_box = (p_int, p_int, ink_w - p_int, ink_h - p_int)
        art_mask = full_mask.crop(mask_box).resize(m["art_size"], Image.LANCZOS)

        # 3. Process Art
        art = Image.open(raw_path).convert("RGBA").resize(m["art_size"], Image.LANCZOS)
        art_clipped = Image.new("RGBA", m["art_size"], (0, 0, 0, 0))
        art_clipped.paste(art, (0, 0), mask=art_mask)

        # 4. Assembly
        # Place frame centered in the gutter
        canvas.alpha_composite(frame_ink, dest=(m["gutter"], m["gutter"]))
        # Place art inside the frame + internal padding
        canvas.alpha_composite(
            art_clipped, dest=(m["gutter"] + p_int, m["gutter"] + p_int)
        )

        if add_shadow:
            canvas = _apply_shadow(canvas)

        canvas.save(output_path, "PNG", optimize=True)
        return True
    except Exception as e:
        logger.error(f"Failed {raw_path.name}: {e}")
        import traceback

        logger.error(traceback.format_exc())  # Helpful for debugging math errors
        return False


def composite_batch(raw_dir, output_dir, svg_path, **kwargs):
    """Orchestrates batch compositing for a deck."""
    from pipeline.manifest import read_metadata

    raw_dir = pathlib.Path(raw_dir)
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    mapping = _load_mapping(kwargs.get("mapping_path"))
    files = _scan_raw(raw_dir)

    succeeded, skipped, failed = 0, 0, 0

    for path in files:
        # Metadata Filtering
        if not kwargs.get("force_raw"):
            meta = mapping.get(path.name) or read_metadata(path)
            if kwargs.get("deck_id") and meta.get("deck_id") != kwargs.get("deck_id"):
                continue
            if kwargs.get("card_names"):
                names = [n.lower() for n in kwargs["card_names"]]
                if meta.get("card_name", "").lower() not in names:
                    continue

        out_path = output_dir / f"{path.stem}.png"
        if out_path.exists() and not kwargs.get("force"):
            skipped += 1
            continue

        success = composite_card(
            raw_path=path,
            svg_path=svg_path,
            output_path=out_path,
            width=kwargs.get("target_size", (734, 1024))[0],
            height=kwargs.get("target_size", (734, 1024))[1],
            pad_edge=kwargs.get("pad_edge"),
            add_shadow=kwargs.get("add_shadow", True),
        )

        if success:
            succeeded += 1
        else:
            failed += 1

    return succeeded, skipped, failed
