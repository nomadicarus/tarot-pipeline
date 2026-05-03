import base64
import io
import logging
import pathlib
import re
from typing import Optional, Tuple

from PIL import Image, ImageFilter

try:
    import cairosvg
except ImportError:
    cairosvg = None

logger = logging.getLogger(__name__)


def _load_frame(svg_path: str, target_size: Tuple[int, int]) -> Image.Image:
    svg_path = pathlib.Path(svg_path)
    svg_text = svg_path.read_text()
    match = re.search(r'data:image/png;base64,([^"\']+)', svg_text)
    if match:
        return Image.open(io.BytesIO(base64.b64decode(match.group(1)))).convert("RGBA")
    if cairosvg is None:
        raise ImportError("Vector SVG detected. Please install: pip install cairosvg")
    png_data = cairosvg.svg2png(url=str(svg_path), output_width=target_size[0] * 2)
    return Image.open(io.BytesIO(png_data)).convert("RGBA")


def _generate_shadow(template: Image.Image, radius: int) -> Image.Image:
    shadow_mask = template.split()[3]
    shadow = Image.new("RGBA", template.size, (0, 0, 0, 0))
    black_layer = Image.new("RGBA", template.size, (0, 0, 0, 150))
    shadow.paste(black_layer, (0, 0), mask=shadow_mask)
    return shadow.filter(ImageFilter.GaussianBlur(radius))


def composite_card(raw_path, svg_path, output_path, **kwargs):
    try:
        width = kwargs.get("width", 1024)
        height = kwargs.get("height", 1024)
        pad_edge = kwargs.get("pad_edge", 0)
        pad_internal = kwargs.get("pad_internal", 0)
        add_shadow = kwargs.get("add_shadow", True)
        s_radius = kwargs.get("shadow_radius", 5)
        s_offset = kwargs.get("shadow_offset", (3, 3))

        # 1. SHADOW AWARENESS: pad_edge 0 cases require buffer if shadow is enabled
        shadow_buffer = s_radius * 2
        effective_pad = max(pad_edge, shadow_buffer) if add_shadow else pad_edge

        temp_w, temp_h = width - (2 * effective_pad), height - (2 * effective_pad)
        art_w, art_h = temp_w - (2 * pad_internal), temp_h - (2 * pad_internal)

        # 2. TEMPLATE & MASK
        template_src = _load_frame(svg_path, (temp_w, temp_h)).resize(
            (temp_w, temp_h), Image.LANCZOS
        )
        template_alpha = template_src.split()[3]
        art_mask = template_alpha.resize((art_w, art_h), Image.LANCZOS)

        # 3. ART
        art_img = (
            Image.open(raw_path).convert("RGBA").resize((art_w, art_h), Image.LANCZOS)
        )

        # 4. ASSEMBLY
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        temp_off = ((width - temp_w) // 2, (height - temp_h) // 2)
        art_off = ((width - art_w) // 2, (height - art_h) // 2)

        if add_shadow:
            shadow_img = _generate_shadow(template_src, s_radius)
            shadow_off = (temp_off[0] + s_offset[0], temp_off[1] + s_offset[1])
            canvas.alpha_composite(shadow_img, dest=shadow_off)

        canvas.alpha_composite(template_src, dest=temp_off)
        canvas.paste(art_img, art_off, mask=art_mask)

        canvas.save(output_path, "PNG", optimize=True)
        return True
    except Exception as e:
        logger.error(f"Failed {pathlib.Path(raw_path).name}: {e}")
        return False


def composite_batch(raw_dir, output_dir, svg_path, **kwargs):
    raw_dir, output_dir = pathlib.Path(raw_dir), pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = [
        p
        for p in raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]

    # Sanitize inputs
    clean_kwargs = {
        "width": int(kwargs.get("width") or 1024),
        "height": int(kwargs.get("height") or 1024),
        "pad_edge": int(kwargs.get("pad_edge") or 0),
        "pad_internal": int(kwargs.get("pad_internal") or 0),
        "add_shadow": kwargs.get("add_shadow", True),
        "shadow_radius": int(kwargs.get("shadow_radius", 5)),
        "shadow_offset": kwargs.get("shadow_offset", (3, 3)),
    }

    s, sk, f = 0, 0, 0
    for path in files:
        out_path = output_dir / f"{path.stem}.png"
        if out_path.exists() and not kwargs.get("force"):
            sk += 1
            continue
        if composite_card(path, svg_path, out_path, **clean_kwargs):
            s += 1
        else:
            f += 1
    return s, sk, f
