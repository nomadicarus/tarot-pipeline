import math
import os
import sys

from PIL import Image


def load_image(p):
    return Image.open(p).convert("RGBA")


def mse(img1, img2):
    # assume same size
    w, h = img1.size
    a = img1.tobytes()
    b = img2.tobytes()
    # compare per-byte
    diff = 0
    for i in range(0, len(a), 4):
        # compute squared error across RGBA channels
        for c in range(4):
            diff += (a[i + c] - b[i + c]) * (a[i + c] - b[i + c])
    return diff / (w * h * 4)


def compare_pair(baseline_path, test_path):
    base = load_image(baseline_path)
    test = load_image(test_path)
    if base.size != test.size:
        # resize test to baseline size for comparison
        test = test.resize(base.size, Image.LANCZOS)
    # compute MSE
    m = mse(base, test)
    # Simple binary mask compare (optional): compute exact pixel-wise equality
    same = 1 if list(base.getdata()) == list(test.getdata()) else 0
    return {
        "baseline": baseline_path,
        "test": test_path,
        "size": base.size,
        "mse": m,
        "exact_match": bool(same),
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: compare_baseline.py <baseline.png> <test1.png> [<test2.png> ...]")
        sys.exit(2)
    baseline = sys.argv[1]
    tests = sys.argv[2:]
    baseline_abs = os.path.abspath(baseline)
    report_lines = []
    for t in tests:
        res = compare_pair(baseline_abs, os.path.abspath(t))
        report_lines.append(
            f"Test {os.path.basename(t)} vs baseline -> size={res['size']}, mse={res['mse']:.6f}, exact_match={res['exact_match']}"
        )
    print("\n".join(report_lines))


if __name__ == "__main__":
    main()
