import pathlib, re
from PIL import Image

svg = pathlib.Path("assets/cardface.svg").read_text()
m = re.search(r'viewBox="([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)"', svg)
if m:
    w, h = float(m.group(3)), float(m.group(4))
    tw, th = 500, 500
    print(f"SVG viewBox: {w}x{h}  aspect={w/h:.4f}")
    print(f"Fixed canvas: {tw}x{th}")
    
    # Frame
    scale = min(tw / w, th / h)
    fw, fh = int(w * scale), int(h * scale)
    print(f"Frame: {fw}x{fh}  offset=({(tw-fw)//2},{(th-fh)//2})")
    
    # Art box with 5% pad-internal (relative to frame width)
    pad_int = 0.05 * fw
    ax0 = (tw - fw) // 2 + int(pad_int)
    ay0 = (th - fh) // 2 + int(pad_int)
    aw = fw - int(pad_int * 2)
    ah = fh - int(pad_int * 2)
    print(f"pad_internal: {pad_int:.1f}px")
    print(f"Art box: x={ax0}, y={ay0}, w={aw}, h={ah}")
    
    art = Image.open("output/thoth/raw/source.png")
    print(f"Raw art: {art.width}x{art.height}")
    
    s_fill = max(aw / art.width, ah / art.height)
    s_contain = min(aw / art.width, ah / art.height)
    print(f"\nFill (default):  scale={s_fill:.4f} -> {int(art.width*s_fill)}x{int(art.height*s_fill)}")
    print(f"Contain (--contain): scale={s_contain:.4f} -> {int(art.width*s_contain)}x{int(art.height*s_contain)}")
