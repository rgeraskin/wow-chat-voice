"""Draws the addon icon: a golden speech bubble with sound waves on a dark arcane background.
Writes addon/WowChatVoice/Icon.tga (64x64, what the game reads) and tools/icon_preview.png.
Run: uv run --with pillow python tools/make_icon.py"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 512                     # drawn large, scaled down for smooth edges
ROOT = Path(__file__).resolve().parents[1]


def radial(size, inner, outer):
    img = Image.new("RGB", (size, size))
    px = img.load()
    c = size / 2
    for y in range(size):
        for x in range(size):
            t = min(1.0, math.hypot(x - c * 0.85, y - c * 0.8) / (size * 0.72))
            px[x, y] = tuple(int(inner[i] + (outer[i] - inner[i]) * t) for i in range(3))
    return img


def main():
    img = radial(S, (52, 40, 92), (8, 6, 20)).convert("RGBA")
    d = ImageDraw.Draw(img)

    # Bevelled frame, like the game's ability icons.
    d.rectangle([0, 0, S - 1, S - 1], outline=(150, 115, 50, 255), width=14)
    d.rectangle([14, 14, S - 15, S - 15], outline=(40, 28, 10, 255), width=6)

    # Speech bubble: shadow, body, tail.
    def bubble(draw, dx, dy, fill):
        draw.rounded_rectangle([70 + dx, 110 + dy, 330 + dx, 330 + dy], radius=95, fill=fill)
        draw.polygon([(120 + dx, 300 + dy), (95 + dx, 420 + dy), (205 + dx, 318 + dy)], fill=fill)

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bubble(ImageDraw.Draw(shadow), 14, 16, (0, 0, 0, 170))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    body = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bubble(ImageDraw.Draw(body), 0, 0, (255, 255, 255, 255))
    gold = Image.new("RGBA", (S, S))
    gp = gold.load()
    for y in range(S):                      # vertical gold gradient
        t = y / S
        gp_row = (int(255 - 60 * t), int(222 - 95 * t), int(120 - 90 * t), 255)
        for x in range(S):
            gp[x, y] = gp_row
    img.paste(gold, (0, 0), body)
    rim = ImageDraw.Draw(img)
    rim.rounded_rectangle([70, 110, 330, 330], radius=95, outline=(110, 70, 20, 255), width=8)

    # Three dots in the bubble: someone is talking.
    for cx in (140, 200, 260):
        rim.ellipse([cx - 20, 200, cx + 20, 240], fill=(70, 40, 10, 255))

    # Sound waves to the right.
    for i, r in enumerate((70, 120, 170)):
        box = [290 - r, 220 - r, 290 + r, 220 + r]
        rim.arc(box, start=-38, end=38, fill=(120, 220, 255, 255 - i * 45), width=24 - i * 4)

    icon = img.resize((64, 64), Image.LANCZOS)
    icon.save(ROOT / "addon" / "WowChatVoice" / "Icon.tga")
    img.resize((256, 256), Image.LANCZOS).save(ROOT / "tools" / "icon_preview.png")
    print("ok")


if __name__ == "__main__":
    main()
