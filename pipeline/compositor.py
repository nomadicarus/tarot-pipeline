import base64
import io
import logging
import pathlib
import re
from pickletools import optimize

from cairosvg.image import image
from PIL import Image, ImageDraw, ImageFilter

try:
    import cairosvg
except ImportError:
    cairosvg = None

logger = logging.getLogger(__name__)


# ---------------------------
# SVG Helpers
# ---------------------------
def _modify_svg_preserve_aspect(svg_path: str, stretch: bool) -> bytes:
    """Return SVG bytes with preserveAspectRatio set for stretch behavior.

    - stretch=True:  set preserveAspectRatio='none' (vector content stretches)
    - stretch=False: set preserveAspectRatio='xMidYMid meet' (aspect preserved)
    """
    import xml.etree.ElementTree as ET

    tree = ET.parse(svg_path)
    root = tree.getroot()
    if stretch:
        root.set("preserveAspectRatio", "none")
    else:
        root.set("preserveAspectRatio", "xMidYMid meet")
    return ET.tostring(root, encoding="utf-8")


# ---------------------------
# Helpers
# ---------------------------
def _get_svg_aspect(svg_path):
    text = pathlib.Path(svg_path).read_text()
    m = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', text)
    if m:
        return float(m.group(1)) / float(m.group(2))
    return 734 / 1024  # fallback


def _frame_native_size(svg_path: str) -> tuple[int, int]:
    """Return the intrinsic dimensions of the template (SVG viewBox or PNG size)."""
    p = pathlib.Path(svg_path)
    if p.suffix.lower() == ".png":
        with Image.open(p) as img:
            return img.size
    if p.suffix.lower() == ".svg":
        text = pathlib.Path(svg_path).read_text()
        m = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', text)
        if m:
            return int(float(m.group(1))), int(float(m.group(2)))
    return 734, 1024  # fallback


def _parse_unit(value, ref):
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).strip().lower()
    m = re.match(r"([+-]?\d*\.?\d+)\s*(px|%)?", value)
    if not m:
        return 0.0
    num, unit = float(m.group(1)), m.group(2)
    return num * ref / 100 if unit == "%" else num


def _load_frame(
    svg_path: str, target_size: tuple[int, int] | None = None, stretch: bool = False
) -> Image.Image:
    p = pathlib.Path(svg_path)
    ext = p.suffix.lower()

    if target_size is None:
        # No sizing requested — return as-is
        if ext == ".png":
            return Image.open(p).convert("RGBA")
        if ext == ".svg":
            if cairosvg is None:
                raise ImportError("cairosvg required for SVG rendering")
            png_bytes = cairosvg.svg2png(url=str(p))
            return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        raise ValueError(f"Unsupported format: {ext}")

    # Determine target render size BEFORE rendering — single resize
    native_w, native_h = _frame_native_size(svg_path)

    if stretch:
        # Stretch: render directly at target_size
        render_w, render_h = target_size
    else:
        # Preserve aspect: fit inside target_size
        scale = min(target_size[0] / native_w, target_size[1] / native_h)
        render_w, render_h = int(native_w * scale), int(native_h * scale)

    # Render at calculated size (single step)
    if ext == ".png":
        img = Image.open(p).convert("RGBA")
        if (img.width, img.height) != (render_w, render_h):
            img = img.resize((render_w, render_h), Image.LANCZOS)

    elif ext == ".svg":
        if cairosvg is None:
            raise ImportError("cairosvg required for SVG rendering")
        # Modify SVG preserveAspectRatio for proper vector stretching
        svg_bytes = _modify_svg_preserve_aspect(str(p), stretch=stretch)
        # Render at target size — SVG vector content is stretched before rasterization
        png_bytes = cairosvg.svg2png(
            bytestring=svg_bytes, output_width=render_w, output_height=render_h
        )
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    else:
        raise ValueError(f"Unsupported format: {ext}")

    # If not stretching, center on target_size canvas
    if not stretch and (render_w, render_h) != target_size:
        centered = Image.new("RGBA", target_size, (0, 0, 0, 0))
        centered.paste(
            img,
            ((target_size[0] - render_w) // 2, (target_size[1] - render_h) // 2),
        )
        return centered

    return img


def _generate_mask(
    svg_path: str,
    render_size: tuple[int, int],
    stretch: bool = False,
    method: str = "alpha",
) -> Image.Image:
    """Render template and return a mask at render_size.

    ALL template types (SVG/PNG) follow the same stretch logic:
      - stretch=True  → render exactly at render_size (--fix-size mode)
      - stretch=False → preserve aspect ratio, center on render_size canvas

    Args:
        svg_path:    Path to SVG or PNG template.
        render_size:  Frame inner size (fw, fh) to render at.
        stretch:      If True, stretch to render_size; else preserve aspect ratio.
        method:       "alpha" (default, clean edges) or "luminance".

    Returns:
        Single-channel ('L') mask image of size render_size.
        White (255) = visible aperture region.
    """
    p = pathlib.Path(svg_path)
    ext = p.suffix.lower()

    # Determine target size BEFORE rendering — resize only once
    native_w, native_h = _frame_native_size(svg_path)
    scale = 1.0

    if stretch:
        # Stretch: target is exactly render_size
        target_w, target_h = render_size
    else:
        # Preserve aspect: fit inside render_size
        scale = min(render_size[0] / native_w, render_size[1] / native_h)
        target_w, target_h = int(native_w * scale), int(native_h * scale)

    # Render template at target size (single resize)
    if ext in (".svg", ".png"):
        if ext == ".svg":
            if cairosvg is None:
                raise ImportError("cairosvg required for SVG rendering")
            # Modify SVG preserveAspectRatio for proper vector stretching
            svg_bytes = _modify_svg_preserve_aspect(str(p), stretch=stretch)
            # Render at target size — SVG vector content is stretched before rasterization
            png_bytes = cairosvg.svg2png(
                bytestring=svg_bytes, output_width=target_w, output_height=target_h
            )
            img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        else:
            # PNG: open and resize to target in one step
            img = Image.open(p).convert("RGBA")
            if (img.width, img.height) != (target_w, target_h):
                img = img.resize((target_w, target_h), Image.LANCZOS)

        # If not stretching, center on render_size canvas
        if not stretch and (target_w, target_h) != render_size:
            centered = Image.new("RGBA", render_size, (0, 0, 0, 0))
            centered.paste(
                img,
                ((render_size[0] - target_w) // 2, (render_size[1] - target_h) // 2),
            )
            img = centered
    else:
        raise ValueError(f"Unsupported template format: {ext}")

    # Extract mask by method
    if method == "alpha":
        # Use alpha channel directly — clean edges, no threshold
        return img.split()[3]

    elif method == "alpha2":
        # Threshold alpha channel: pixels with alpha >= 128 become white
        # (previous implementation used an impossible threshold v > 255)
        alpha = img.split()[3]
        return alpha.point(lambda v: 255 if v >= 200 else 0)

    elif method == "luma":
        # Luma = (0.2126*R + 0.7152*G + 0.0722*B) * A/255
        # Pixel-by-pixel calculation (mask generation, performance not critical)
        luma = Image.new("L", img.size, 0)
        pixels = luma.load()
        src = img.load()
        for x in range(img.width):
            for y in range(img.height):
                px = src[x, y]
                val = int(
                    (0.2126 * px[0] + 0.7152 * px[1] + 0.0722 * px[2]) * px[3] / 255
                )
                pixels[x, y] = min(255, max(0, val))
        return luma.point(lambda v: 255 if v > 128 else 0)

    elif method == "legacy" or method == "legacy_mask":
        # Backward-compat: derive mask from grayscale threshold on rendered frame
        grey = img.convert("L")
        return grey.point(lambda p: 255 if p > 200 else 0)
    else:
        raise ValueError(
            f"Unknown mask method: {method}. Use 'alpha', 'alpha2', 'luma', or 'legacy'."
        )


def composite_card(raw_path, svg_path, output_path, **kw):
    try:
        frame_raw = _load_frame(svg_path)

        fixed = kw.get("fixed", False)

        # --- sizing ---
        if fixed:
            tw, th = kw["fix_size"]
        else:
            ew, eh = kw["size"]
            nw, nh = _frame_native_size(svg_path)
            # 0 means unconstrained for that dimension
            if ew == 0 and eh > 0:
                scale = eh / nh
                tw, th = int(nw * scale), eh
            elif eh == 0 and ew > 0:
                scale = ew / nw
                tw, th = ew, int(nh * scale)
            else:
                scale_w = ew / nw if ew else 0
                scale_h = eh / nh if eh else 0
                scale = max(scale_w, scale_h, 0.0)
                if scale == 0:
                    scale = 1.0
                tw, th = int(nw * scale), int(nh * scale)

        canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))

        # --- edge padding ---
        pad_edge = _parse_unit(kw.get("pad_edge", 0), tw)

        # Frame fills canvas minus pad_edge
        fw = tw - int(pad_edge * 2)
        fh = th - int(pad_edge * 2)
        frame = _load_frame(svg_path, (fw, fh), stretch=fixed)
        fx = int(pad_edge)
        fy = int(pad_edge)

        # --- shadow ---
        if kw.get("add_shadow", True):
            radius = _parse_unit(kw.get("shadow_radius", 3.8), fw)
            offset_x = _parse_unit(kw.get("shadow_offset_x", 1.5), fw)
            offset_y = _parse_unit(kw.get("shadow_offset_y", 1.5), fh)
            opacity = kw.get("shadow_opacity", 150)

            alpha = frame.split()[3]
            shadow = Image.new("L", (fw, fh), 0)
            shadow.paste(alpha, (0, 0))
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius))

            shadow_rgba = Image.new("RGBA", (fw, fh), (0, 0, 0, opacity))
            shadow_rgba.putalpha(shadow)

            canvas.paste(
                shadow_rgba,
                (int(fx + offset_x), int(fy + offset_y)),
                shadow_rgba,
            )

        # --- art box ---
        pad_int = _parse_unit(kw.get("pad_internal", 48), fw)

        ax0 = fx + int(pad_int)
        ay0 = fy + int(pad_int)
        aw = fw - int(pad_int * 2)
        ah = fh - int(pad_int * 2)

        art = Image.open(raw_path).convert("RGBA")

        if kw.get("contain"):
            s = min(aw / art.width, ah / art.height)
        else:
            s = max(aw / art.width, ah / art.height)

        s *= kw.get("scale", 1.0)

        art = art.resize((int(art.width * s), int(art.height * s)), Image.LANCZOS)

        nudge = str(kw.get("nudge", "0,0")).split(",")
        nx = _parse_unit(nudge[0], fw)
        ny = _parse_unit(nudge[1], fh)

        px = ax0 + (aw - art.width) // 2 + int(nx)
        py = ay0 + (ah - art.height) // 2 + int(ny)

        # --- mask: render at frame inner size, resize to art box ---
        art_layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        art_layer.paste(art, (px, py), art)

        # Render mask at frame inner size (matches frame render)
        mask_method = kw.get("mask_method", "alpha")
        mask_full = _generate_mask(
            svg_path, render_size=(fw, fh), stretch=fixed, method=mask_method
        )

        if pad_int > 0:
            # Resize mask from frame inner to art box (LANCZOS preserves edges)
            mask_target = mask_full.resize((aw, ah), Image.LANCZOS)
        else:
            mask_target = mask_full

        full_mask = Image.new("L", (tw, th), 0)
        full_mask.paste(mask_target, (ax0, ay0))
        full_mask = full_mask.resize((tw, th), Image.LANCZOS)
        # full_mask = full_mask.filter(ImageFilter.SMOOTH_MORE)
        full_mask = full_mask.filter(ImageFilter.GaussianBlur(radius=.8))

        art_layer.putalpha(full_mask)

        # --- final ---
        canvas.paste(frame, (fx, fy), frame)
        # canvas.paste(a_layer, (0,0), a_layer)
        canvas.paste(art_layer, (0, 0), art_layer)

        canvas.save(output_path, "PNG", optimize=True)
        return True

    except Exception as e:
        logger.error(f"{raw_path.name}: {e}")
        return False


def composite_batch(raw_dir, output_dir, svg_path, mask_method="alpha", **kw):
    raw_dir = pathlib.Path(raw_dir)
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    s = sk = f = 0

    for file in raw_dir.iterdir():
        if file.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue

        out = output_dir / f"{file.stem}.png"

        if out.exists() and not kw.get("force"):
            sk += 1
            continue

        if composite_card(file, svg_path, out, mask_method=mask_method, **kw):
            s += 1
        else:
            f += 1

    return s, sk, f
