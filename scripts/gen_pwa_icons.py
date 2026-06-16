"""Generate placeholder PWA icons (brand-blue tooth) into static/icons/.

These are intentionally simple placeholders — replace with a designed icon when
available. Run: python scripts/gen_pwa_icons.py
"""
import os
from PIL import Image, ImageDraw

BRAND = (13, 110, 253, 255)   # Bootstrap primary blue (matches navbar bg-primary)
WHITE = (255, 255, 255, 255)
OUT = os.path.join("static", "icons")


def _draw_tooth(d, size, inset):
    """Draw a simple white tooth centred in a square, within `inset` padding."""
    box = size - 2 * inset
    cx = size / 2
    top = inset
    tw = box * 0.62          # tooth width
    th = box * 0.82          # tooth height
    left, right = cx - tw / 2, cx + tw / 2
    bottom = top + th
    # Crown + body: a rounded rectangle with a strongly rounded top.
    d.rounded_rectangle([left, top, right, bottom], radius=tw * 0.45, fill=WHITE)
    # Notch at the bottom centre to split the roots in two.
    notch_w = tw * 0.20
    d.polygon(
        [(cx - notch_w, bottom), (cx + notch_w, bottom), (cx, top + th * 0.55)],
        fill=BRAND,
    )


def make_icon(size, maskable=False):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if maskable:
        # Full-bleed background; keep the glyph inside the ~80% safe zone.
        d.rectangle([0, 0, size, size], fill=BRAND)
        _draw_tooth(d, size, inset=size * 0.26)
    else:
        d.rounded_rectangle([0, 0, size, size], radius=size * 0.18, fill=BRAND)
        _draw_tooth(d, size, inset=size * 0.20)
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    make_icon(192).save(os.path.join(OUT, "icon-192.png"))
    make_icon(512).save(os.path.join(OUT, "icon-512.png"))
    make_icon(512, maskable=True).save(os.path.join(OUT, "maskable-512.png"))
    print("Wrote icon-192.png, icon-512.png, maskable-512.png to", OUT)


if __name__ == "__main__":
    main()
