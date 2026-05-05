import base64
import io
import logging
import pathlib
import re

from PIL import Image, ImageFilter

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


def _parse_unit(value, ref):
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).strip().lower()
    m = re.match(r"([+-]?\d*\.?\d+)\s*(px|%)?", value)
    if not m:
        return 0.0
    num, unit = float(m.group(1)), m.group(2)
    return num * ref / 100 if unit == "%" else num


def _load_frame(svg_path: str, target_size: tuple[int, int]) -> Image.Image:
    p = pathlib.Path(svg_path)
    ext = p.suffix.lower()

    # PNG path (simple)
    if ext == ".png":
        return Image.open(p).convert("RGBA").resize(target_size, Image.LANCZOS)

    if ext == ".svg":
        if cairosvg is None:
            raise ImportError("cairosvg required for SVG rendering")

        png_bytes = cairosvg.svg2png(
            url=str(p),
            output_width=target_size[0],
            output_height=target_size[1],
        )

        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    raise ValueError(f"Unsupported format: {ext}")


def composite_card(raw_path, svg_path, output_path, **kw):
    try:
        frame_raw = _load_frame(svg_path)

        fixed = kw.get("fixed", False)

        # --- sizing ---
        if fixed:
            tw, th = kw["width_f"], kw["height_f"]
        else:
            tw, th = kw["width"], kw["height"]

        canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))

        # --- edge padding ---
        pad_edge = _parse_unit(kw.get("pad_edge", 0), tw)

        # --- frame scaling ---
        scale = min(
            (tw - pad_edge * 2) / frame_raw.width,
            (th - pad_edge * 2) / frame_raw.height,
        )

        fw, fh = int(frame_raw.width * scale), int(frame_raw.height * scale)
        frame = _load_frame(svg_path, (fw, fh))

        fx = (tw - fw) // 2
        fy = (th - fh) // 2

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

        if kw.get("f_crop"):
            s = max(aw / art.width, ah / art.height)
        else:
            s = min(aw / art.width, ah / art.height)

        s *= kw.get("art_scale", 1.0)

        art = art.resize((int(art.width * s), int(art.height * s)), Image.LANCZOS)

        nx = _parse_unit(kw.get("art_nudge", ("0", "0"))[0], fw)
        ny = _parse_unit(kw.get("art_nudge", ("0", "0"))[1], fh)

        px = ax0 + (aw - art.width) // 2 + int(nx)
        py = ay0 + (ah - art.height) // 2 + int(ny)

        # --- mask ONLY inside art box ---
        art_layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        art_layer.paste(art, (px, py), art)

        mask = Image.new("L", (tw, th), 0)
        frame_alpha = frame.split()[3]

        # CRITICAL: crop inner mask, do NOT scale whole frame
        inner_mask = frame_alpha.crop(
            (
                int(pad_int),
                int(pad_int),
                int(fw - pad_int),
                int(fh - pad_int),
            )
        )

        mask.paste(inner_mask, (ax0, ay0))

        art_layer.putalpha(mask)

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
