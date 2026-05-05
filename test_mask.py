import io
import os
from PIL import Image
import cairosvg

# Test harness for mask application

CANVAS_W, CANVAS_H = 834, 1124
ART_SRC = os.path.abspath(os.path.join(os.getcwd(), 'output','thoth','raw','source.png'))
OUTPUT_DIR = os.path.abspath("test")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def render_mask(template_path, width, height, out_mask_path):
    # Render mask frame from template (SVG or PNG) to target canvas size
    svg = template_path
    png_bytes = cairosvg.svg2png(url=svg, output_width=width, output_height=height)
    frame = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    frame.save(out_mask_path)
    return frame

def main():
    template = os.path.abspath("assets/cardface.svg");
    # 1) render mask frame at canvas size
    mask_img_path = os.path.join(OUTPUT_DIR, "mask_frame_834x1124.png")
    mask_frame = render_mask(template, CANVAS_W, CANVAS_H, mask_img_path)

    # 2) create mask (white = visible, black = hidden) from alpha
    mask = mask_frame.split()[3].convert("L")
    mask_path = os.path.join(OUTPUT_DIR, "mask_only_834x1124.png")
    mask.save(mask_path)

    # 3) prepare artwork - load and double size then fit into mask interior
    art = Image.open(ART_SRC).convert("RGBA")
    art2 = art.resize((art.width*2, art.height*2), Image.LANCZOS)
    # place art in the center of the canvas, clipped by mask
    final = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0,0,0,0))
    # compute placement: center art2 within the canvas
    x = (CANVAS_W - art2.width)//2
    y = (CANVAS_H - art2.height)//2
    final.paste(art2, (x,y), art2)
    # apply mask to final art portion only
    final.putalpha(mask)

    out_final = os.path.join(OUTPUT_DIR, "test_mask_final.png")
    final.save(out_final)
    print("Mask test completed. Outputs:")
    print("mask_frame:", mask_img_path)
    print("mask_only:", mask_path)
    print("test_mask_final:", out_final)

if __name__ == '__main__':
    main()
