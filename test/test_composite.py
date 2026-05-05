"""
Test: Generate mask from SVG at original dimensions, then resize raster vs vector stretch
Command: --composite --deck thoth --size 0,1024 --pad-internal 8% --pad-edge 0 --force --scale 1.0 --template assets/cardface.svg
"""
import sys
import pathlib
import xml.etree.ElementTree as ET
import cairosvg
import io
from PIL import Image, ImageFilter

def _frame_native_size(svg_path):
    p = pathlib.Path(svg_path)
    if p.suffix.lower() == ".svg":
        text = p.read_text()
        import re
        m = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', text)
        if m:
            return int(float(m.group(1))), int(float(m.group(2)))
    return 734, 1024

def modify_svg_preserve_aspect(svg_path, stretch):
    tree = ET.parse(svg_path)
    root = tree.getroot()
    if stretch:
        root.set("preserveAspectRatio", "none")
    else:
        root.set("preserveAspectRatio", "xMidYMid meet")
    return ET.tostring(root, encoding="utf-8")

def test_method_1_vector_stretch(svg_path, render_size):
    """Method 1: Stretch vector, then rasterize (correct way)"""
    svg_bytes = modify_svg_preserve_aspect(svg_path, stretch=True)
    png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=render_size[0], output_height=render_size[1])
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    return img.split()[3]  # Return alpha mask

def test_method_2_raster_resize(svg_path, render_size):
    """Method 2: Render at native size, then resize raster (old way)"""
    native_w, native_h = _frame_native_size(svg_path)
    # Render at native size
    png_bytes = cairosvg.svg2png(url=svg_path, output_width=native_w, output_height=native_h)
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    # Resize raster
    img = img.resize(render_size, Image.LANCZOS)
    return img.split()[3]  # Return alpha mask

def main():
    svg_path = "assets/cardface.svg"
    deck = "thoth"
    size = (0, 1024)  # 0 means auto-calculate from native size
    pad_internal = "8%"
    pad_edge = 0
    scale = 1.0

    # Calculate target size (mimicking compositor logic)
    native_w, native_h = _frame_native_size(svg_path)
    # size = (0, 1024) means height=1024, width auto
    th = 1024
    tw = int(native_w * (th / native_h))  # Preserve aspect
    target_size = (tw, th)
    print(f"Target size (native aspect): {target_size}")

    # For testing stretch difference, also test with force-stretched size
    stretch_size = (1024, 1024)  # Square - forces stretching!
    print(f"Stretch test size: {stretch_size}")

    # Calculate art box (after pad_internal)
    pad_int_px = int(float(pad_internal.strip('%')) / 100 * target_size[0])
    aw = target_size[0] - int(pad_int_px * 2)
    ah = target_size[1] - int(pad_int_px * 2)
    print(f"Art box size: {aw}x{ah}")

    out = pathlib.Path("test")
    out.mkdir(exist_ok=True)

    # Test at native aspect size (should be identical)
    print("\n--- Test at native aspect (734x1024) ---")

    # Method 1: Vector stretch
    print("Method 1: Vector stretch (modify SVG preserveAspectRatio)")
    mask1 = test_method_1_vector_stretch(svg_path, target_size)
    mask1.save(out / "test_composite_method1_full.png")
    # Resize mask to art box
    mask1_art = mask1.resize((aw, ah), Image.NEAREST)
    mask1_art.save(out / "test_composite_method1_art.png")
    print(f"  Full mask: {mask1.size}")
    print(f"  Art mask: {mask1_art.size}")

    # Method 2: Raster resize
    print("\nMethod 2: Raster resize (render native, then resize)")
    mask2 = test_method_2_raster_resize(svg_path, target_size)
    mask2.save(out / "test_composite_method2_full.png")
    # Resize mask to art box
    mask2_art = mask2.resize((aw, ah), Image.NEAREST)
    mask2_art.save(out / "test_composite_method2_art.png")
    print(f"  Full mask: {mask2.size}")
    print(f"  Art mask: {mask2_art.size}")

    # Compare: check if masks are different
    if list(mask1.getdata()) == list(mask2.getdata()):
        print("\nMasks are IDENTICAL (expected at native size)")
    else:
        print("\nMasks are DIFFERENT!")

    # Now test with STRETCHED size (1024x1024)
    print("\n--- Test at STRETCHED size (1024x1024) ---")

    # Method 1: Vector stretch
    print("\nMethod 1: Vector stretch at 1024x1024")
    mask1s = test_method_1_vector_stretch(svg_path, stretch_size)
    mask1s.save(out / "test_composite_method1_stretched.png")
    print(f"  Size: {mask1s.size}")

    # Method 2: Raster resize
    print("Method 2: Raster resize to 1024x1024")
    mask2s = test_method_2_raster_resize(svg_path, stretch_size)
    mask2s.save(out / "test_composite_method2_stretched.png")
    print(f"  Size: {mask2s.size}")

    # Compare stretched masks
    if list(mask1s.getdata()) == list(mask2s.getdata()):
        print("\nStretched masks are IDENTICAL (unexpected!)")
    else:
        print("\nStretched masks are DIFFERENT - vector stretch matters!")

    # Output file as requested
    print("\n--- Generating output: /test/ughghghg.png ---")
    # Create composite showing the difference
    diff_img = Image.new("RGBA", stretch_size, (0, 0, 0, 0))
    color1 = Image.new("RGBA", stretch_size, (255, 0, 0, 128))  # Red for vector
    color2 = Image.new("RGBA", stretch_size, (0, 0, 255, 128))  # Blue for raster
    diff_img.paste(color1, (0, 0), mask1s)
    diff_img.paste(color2, (0, 0), mask2s)
    diff_img.save(out / "ughghghg.png")
    print(f"Saved: {out / 'ughghghg.png'}")

    # Save composite output (frame + mask)
    print("\nSaving composite outputs...")
    # Create a test composite image showing the mask
    test_img = Image.new("RGBA", target_size, (0, 0, 0, 0))
    # Create a colored overlay using mask1
    color_overlay = Image.new("RGBA", target_size, (255, 0, 0, 128))
    test_img.paste(color_overlay, (0, 0), mask1)
    test_img.save(out / "test_composite_final.png")
    print(f"Saved: {out / 'test_composite_final.png'}")

if __name__ == "__main__":
    main()
