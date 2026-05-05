"""
Test: Composite with vector scaling, apply Gaussian blur to mask
Args: --composite --deck thoth --size 0,1024 --pad-internal 8% --pad-edge 0 --force --scale 1.0 --template assets/cardface.svg
"""
import sys
import pathlib
import math
from PIL import Image, ImageDraw, ImageFilter

# Add parent to path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from pipeline.compositor import (
    _load_frame, _generate_mask, _frame_native_size, _parse_unit
)

def composite_with_blur(raw_path, svg_path, output_path, blur_radius=0, **kw):
    """Composite card with optional Gaussian blur on mask."""
    try:
        fixed = kw.get("fixed", False)

        # --- sizing ---
        if fixed:
            tw, th = kw["fix_size"]
        else:
            ew, eh = kw["size"]
            nw, nh = _frame_native_size(svg_path)
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

        # --- mask with optional blur ---
        art_layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        art_layer.paste(art, (px, py), art)

        # Generate mask at frame inner size
        mask_method = kw.get("mask_method", "alpha")
        mask_full = _generate_mask(
            svg_path, render_size=(fw, fh), stretch=fixed, method=mask_method
        )

        # Apply Gaussian blur to mask if specified
        if blur_radius > 0:
            mask_full = mask_full.filter(ImageFilter.GaussianBlur(blur_radius))

        if pad_int > 0:
            mask_target = mask_full.resize((aw, ah), Image.NEAREST)
        else:
            mask_target = mask_full

        full_mask = Image.new("L", (tw, th), 0)
        full_mask.paste(mask_target, (ax0, ay0))
        art_layer.putalpha(full_mask)

        # --- final ---
        canvas.paste(frame, (fx, fy), frame)
        canvas.paste(art_layer, (0, 0), art_layer)

        canvas.save(output_path, "PNG")
        return True

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    svg_path = "assets/cardface.svg"
    raw_dir = pathlib.Path("decks/thoth")  # Assuming thoth deck exists
    out_dir = pathlib.Path("test")
    out_dir.mkdir(exist_ok=True)

    # Find first image in thoth deck
    raw_files = list(raw_dir.glob("*.png")) + list(raw_dir.glob("*.jpg"))
    if not raw_files:
        print(f"No images found in {raw_dir}")
        # Try to find any image
        raw_files = list(pathlib.Path(".").rglob("*.png"))[:1]
        if not raw_files:
            print("No images found, creating test image...")
            test_img = Image.new("RGBA", (512, 768), (100, 150, 200, 255))
            raw_path = out_dir / "test_art.png"
            test_img.save(raw_path)
            raw_files = [raw_path]

    raw_path = raw_files[0]
    print(f"Using art: {raw_path}")

    # Test parameters
    blur_values = [0.1, 0.5, 1, 2]

    for blur in blur_values:
        out_path = out_dir / f"composite_blur_{str(blur).replace('.', '_')}.png"
        print(f"\nTesting blur={blur} -> {out_path.name}")

        result = composite_with_blur(
            raw_path,
            svg_path,
            out_path,
            blur_radius=blur,
            fixed=False,
            size=(0, 1024),
            pad_internal="8%",
            pad_edge=0,
            scale=1.0,
            force=True,
            add_shadow=True,
            shadow_radius=3.8,
            shadow_offset_x=1.5,
            shadow_offset_y=1.5,
            shadow_opacity=150,
            mask_method="alpha",
        )

        if result:
            print(f"  Saved: {out_path}")
        else:
            print(f"  FAILED")


if __name__ == "__main__":
    main()
