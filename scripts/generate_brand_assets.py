"""
Generate brand assets for Holistic Vet Directory.

Outputs:
  static/images/og-image.png   1200x630 social share card
  static/images/favicon.png    192x192 PNG favicon
  static/images/favicon.svg    Vector favicon
  static/favicon.ico           Multi-size ICO (16/32/48) shipped to site root

Run from project root: python scripts/generate_brand_assets.py
Re-run any time the brand mark changes.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(__file__).resolve().parent.parent
IMAGES = PROJECT / "static" / "images"
STATIC = PROJECT / "static"
IMAGES.mkdir(parents=True, exist_ok=True)

FOREST = (45, 106, 79)
SAGE = (82, 183, 136)
CREAM = (248, 246, 240)
WHITE = (255, 255, 255)
DARK = (26, 51, 38)


def find_font(candidates, size):
    for name in candidates:
        for prefix in ("/System/Library/Fonts/", "/System/Library/Fonts/Supplemental/", "/Library/Fonts/"):
            p = Path(prefix + name)
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), size)
                except OSError:
                    pass
    return ImageFont.load_default()


BOLD = ["HelveticaNeue.ttc", "Helvetica.ttc", "Arial Bold.ttf", "Arial.ttf"]
REG = ["HelveticaNeue.ttc", "Helvetica.ttc", "Arial.ttf"]


def draw_paw(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float, fill):
    """Stylized paw print: 4 toe pads + main pad."""
    s = scale
    # Main pad
    draw.ellipse([cx - 60 * s, cy - 10 * s, cx + 60 * s, cy + 75 * s], fill=fill)
    # Toe pads (top row)
    draw.ellipse([cx - 75 * s, cy - 70 * s, cx - 35 * s, cy - 25 * s], fill=fill)
    draw.ellipse([cx - 30 * s, cy - 90 * s, cx + 5 * s, cy - 50 * s], fill=fill)
    draw.ellipse([cx + 10 * s, cy - 90 * s, cx + 45 * s, cy - 50 * s], fill=fill)
    draw.ellipse([cx + 50 * s, cy - 70 * s, cx + 90 * s, cy - 25 * s], fill=fill)


def og_image():
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), FOREST)
    d = ImageDraw.Draw(img)

    # Sage accent bar across the top
    d.rectangle([0, 0, W, 14], fill=SAGE)

    # Centered paw mark above wordmark
    draw_paw(d, W // 2, 200, 1.0, SAGE)

    title_font = find_font(BOLD, 96)
    sub_font = find_font(REG, 40)
    domain_font = find_font(REG, 28)

    title = "Holistic Vet Directory"
    sub = "Find a Holistic or Integrative Vet"
    domain = "holisticvetdirectory.com"

    def text_w(text, font):
        bbox = d.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

    title_y = 320
    sub_y = 440
    domain_y = 520

    d.text(((W - text_w(title, title_font)) // 2, title_y), title, font=title_font, fill=WHITE)
    d.text(((W - text_w(sub, sub_font)) // 2, sub_y), sub, font=sub_font, fill=CREAM)
    d.text(((W - text_w(domain, domain_font)) // 2, domain_y), domain, font=domain_font, fill=SAGE)

    out = IMAGES / "og-image.png"
    img.save(out, "PNG", optimize=True)
    print(f"  wrote {out.relative_to(PROJECT)}  ({out.stat().st_size // 1024} KB)")


def favicon_png(size=192):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Rounded square background
    pad = size // 16
    d.rounded_rectangle([pad, pad, size - pad, size - pad], radius=size // 6, fill=FOREST)
    # White paw centered
    draw_paw(d, size // 2, size // 2 + size // 16, size / 220, WHITE)
    return img


def favicon_files():
    big = favicon_png(192)
    out_png = IMAGES / "favicon.png"
    big.save(out_png, "PNG", optimize=True)
    print(f"  wrote {out_png.relative_to(PROJECT)}  ({out_png.stat().st_size // 1024} KB)")

    # Multi-size ICO (16, 32, 48)
    ico_sizes = [(16, 16), (32, 32), (48, 48)]
    out_ico = STATIC / "favicon.ico"
    big.save(out_ico, format="ICO", sizes=ico_sizes)
    print(f"  wrote {out_ico.relative_to(PROJECT)}  ({out_ico.stat().st_size // 1024} KB)")


def favicon_svg():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect x="2" y="2" width="60" height="60" rx="10" fill="#2D6A4F"/>
  <g fill="#FFFFFF">
    <ellipse cx="32" cy="40" rx="14" ry="11"/>
    <ellipse cx="19" cy="26" rx="6" ry="7"/>
    <ellipse cx="27" cy="18" rx="5" ry="6"/>
    <ellipse cx="37" cy="18" rx="5" ry="6"/>
    <ellipse cx="45" cy="26" rx="6" ry="7"/>
  </g>
</svg>
"""
    out = IMAGES / "favicon.svg"
    out.write_text(svg)
    print(f"  wrote {out.relative_to(PROJECT)}  ({out.stat().st_size} B)")


if __name__ == "__main__":
    print("Generating brand assets...")
    og_image()
    favicon_files()
    favicon_svg()
    print("Done.")
