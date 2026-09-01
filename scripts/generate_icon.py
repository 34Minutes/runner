"""Generate assets/icon.ico (Windows executable icon).

Run this on Windows (or any machine with Pillow):

    pip install pillow
    python scripts/generate_icon.py

It produces a multi-size .ico with a clean arrow that matches the app's trigger widget
(dark rounded background + blue downward chevron accent).
"""

from __future__ import annotations

from PIL import Image, ImageDraw
import os


def make_arrow(size: int) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    s = size / 256.0
    margin = max(2, int(8 * s))
    radius = max(6, int(46 * s))

    # Dark rounded background (very close to the floating trigger)
    d.rounded_rectangle(
        [margin, margin, size - margin - 1, size - margin - 1],
        radius=radius,
        fill=(28, 28, 30, 255),
    )

    # App accent blue arrow
    blue = (10, 132, 255, 255)
    cx = size // 2
    cy = int(size * 0.505)
    asz = int(70 * s)
    thickness = max(3, int(9 * s))

    # Downward chevron
    p1 = (cx - int(asz * 0.58), cy - int(asz * 0.26))
    p2 = (cx, cy + int(asz * 0.52))
    p3 = (cx + int(asz * 0.58), cy - int(asz * 0.26))

    d.line([p1, p2], fill=blue, width=thickness)
    d.line([p2, p3], fill=blue, width=thickness)

    # Small cap/dot at the point for polish at larger sizes
    if size >= 48:
        r = max(1, int(4.5 * s))
        d.ellipse([cx - r, p2[1] - r, cx + r, p2[1] + r], fill=blue)

    return im


def main() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets_dir = os.path.join(project_root, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    sizes = [256, 128, 64, 48, 32, 24, 16]
    icons = [make_arrow(sz) for sz in sizes]

    out_path = os.path.join(assets_dir, "icon.ico")
    icons[0].save(
        out_path,
        "ICO",
        append_images=icons[1:],
        sizes=[(im.width, im.height) for im in icons],
    )

    print(f"Generated {out_path}")
    print(f"  Size on disk: {os.path.getsize(out_path)} bytes")
    print(f"  Sizes: {sizes}")


if __name__ == "__main__":
    main()
