import base64
import io
import logging
import pathlib
import re

from PIL import Image, ImageDraw, ImageFilter

try:
    import cairosvg
except ImportError:
    cairosvg = None

logger = logging.getLogger(__name__)


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


def _load_frame(svg_path: str, target_size: tuple[int, int] | None = None, stretch: bool = False) -> Image.Image:
    p = pathlib.Path(svg_path)
    ext = p.suffix.lower()

    if ext == ".png":
        img = Image.open(p).convert("RGBA")
        if target_size:
            return img.resize(target_size, Image.LANCZOS)
        return img

    if ext == ".svg":
        if cairosvg is None:
            raise ImportError("cairosvg required for SVG rendering")

        kwargs = {}
        if target_size and not stretch:
            kwargs["output_width"] = target_size[0]
            kwargs["output_height"] = target_size[1]

        png_bytes = cairosvg.svg2png(url=str(p), **kwargs)
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

        if target_size and stretch:
            img = img.resize(target_size, Image.LANCZOS)

        return img

    raise ValueError(f"Unsupported format: {ext}")


def _extract_inner_mask(frame: Image.Image) -> Image.Image:
    """Extract the inner aperture mask from the rendered frame.

    The card interior is bright white, the border stroke is dark.
    Threshold the luminance to get the inner aperture shape including
    curved corners.
    """
    grey = frame.convert("L")
    mask = grey.point(lambda p: 255 if p > 200 else 0)
    return mask


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
            scale_w = ew / nw if ew else 0
            scale_h = eh / nh if eh else 0
            scale = max(scale_w, scale_h, 1.0)
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

        # --- mask ONLY inside art box ---
        art_layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        art_layer.paste(art, (px, py), art)

        # Extract inner aperture mask from frame luminance
        inner_mask = _extract_inner_mask(frame)

        # Position inner_mask on a full-canvas mask
        full_mask = Image.new("L", (tw, th), 0)
        full_mask.paste(inner_mask, (fx, fy))

        # Apply mask to art layer
        art_layer.putalpha(full_mask)

        # --- final ---
        canvas.paste(frame, (fx, fy), frame)
        canvas.paste(art_layer, (0, 0), art_layer)

        canvas.save(output_path, "PNG")
        return True

    except Exception as e:
        logger.error(f"{raw_path.name}: {e}")
        return False


def composite_batch(raw_dir, output_dir, svg_path, **kw):
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

        if composite_card(file, svg_path, out, **kw):
            s += 1
        else:
            f += 1

    return s, sk, f
