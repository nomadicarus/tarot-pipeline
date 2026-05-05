import pathlib
import io
from PIL import Image
import cairosvg

SVG_PATH = "assets/cardface.svg"
OUT_DIR = pathlib.Path("output/thoth/test")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Test heights with preserved aspect ratio
native_w, native_h = 734, 1024
ratio = native_w / native_h

heights = [512, 1024, 2048]

for h in heights:
    w = int(h * ratio)

    print(f"\n--- Height={h}, Width={w} (aspect {ratio:.4f}) ---")

    png_bytes = cairosvg.svg2png(
        url=SVG_PATH,
        output_width=w,
        output_height=h,
    )

    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    print(f"  Rendered: {img.size[0]}x{img.size[1]}")

    rgba_path = OUT_DIR / f"test_h{h}_rgba.png"
    img.save(rgba_path, "PNG")
    print(f"  Saved RGBA: {rgba_path}")

    # Extract alpha: white where alpha > 0, black where alpha == 0
    alpha = img.split()[3]
    mask = Image.new("RGB", alpha.size, (0, 0, 0))
    mask.paste(Image.new("RGB", alpha.size, (255, 255, 255)), (0, 0), alpha)
    mask_path = OUT_DIR / f"test_h{h}_mask.png"
    mask.save(mask_path, "PNG")
    print(f"  Saved mask: {mask_path}")

# Test fixed 500x500 (no aspect preservation)
print(f"\n--- Fixed 500x500 (no aspect preservation) ---")
png_bytes = cairosvg.svg2png(url=SVG_PATH, output_width=500, output_height=500)
img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
print(f"  Rendered: {img.size[0]}x{img.size[1]}")

rgba_path = OUT_DIR / f"test_fixed_500x500_rgba.png"
img.save(rgba_path, "PNG")
print(f"  Saved RGBA: {rgba_path}")

alpha = img.split()[3]
mask = Image.new("RGB", alpha.size, (0, 0, 0))
mask.paste(Image.new("RGB", alpha.size, (255, 255, 255)), (0, 0), alpha)
mask_path = OUT_DIR / f"test_fixed_500x500_mask.png"
mask.save(mask_path, "PNG")
print(f"  Saved mask: {mask_path}")

print("\nDone.")
