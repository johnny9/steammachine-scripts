#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/liberation-fonts/LiberationSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default(size=size)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "game"


def star_points(cx: float, cy: float, r1: float, r2: float) -> list[tuple[float, float]]:
    return [
        (
            cx + math.cos(-math.pi / 2 + i * math.pi / 5) * (r1 if i % 2 == 0 else r2),
            cy + math.sin(-math.pi / 2 + i * math.pi / 5) * (r1 if i % 2 == 0 else r2),
        )
        for i in range(10)
    ]


def generic_scene(width: int, height: int, seed: str) -> Image.Image:
    random.seed(seed)
    img = Image.new("RGBA", (width, height), "#7bc8ff")
    d = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(1, height - 1)
        d.line([(0, y), (width, y)], fill=(int(70 + 90 * t), int(175 + 45 * t), 255, 255))

    for cx, cy, scale in [(0.18, 0.16, 0.08), (0.48, 0.11, 0.06), (0.78, 0.18, 0.09)]:
        px, py, s = cx * width, cy * height, scale * width
        for ox, oy, rr in [(-0.8, 0.1, 0.55), (-0.25, -0.1, 0.72), (0.35, 0, 0.58), (0.9, 0.14, 0.42)]:
            d.ellipse((px + ox * s, py + oy * s, px + (ox + rr) * s, py + (oy + rr * 0.62) * s), fill=(255, 255, 255, 190))

    for color, base, amp, phase in [("#78d760", 0.68, 0.15, -0.1), ("#4ab858", 0.78, 0.20, 0.25), ("#237d42", 0.88, 0.23, -0.2)]:
        pts = [(0, height)]
        for x in range(0, width + 14, 14):
            y = height * base - math.sin((x / width + phase) * math.pi * 2) * height * amp
            pts.append((x, y))
        pts.extend([(width, height), (0, height)])
        d.polygon(pts, fill=color)

    cx = width * 0.5
    gy = height * 0.79
    stone = "#d8b57c"
    outline = "#8f6b42"
    roof = "#c84235"
    for x0, y0, x1, y1 in [
        (cx - width * 0.13, height * 0.45, cx + width * 0.13, gy),
        (cx - width * 0.29, height * 0.55, cx - width * 0.12, gy),
        (cx + width * 0.12, height * 0.55, cx + width * 0.29, gy),
    ]:
        d.rounded_rectangle((x0, y0, x1, y1), radius=max(3, width // 120), fill=stone, outline=outline, width=max(2, width // 240))
    for tx, tw, top in [(cx, width * 0.31, height * 0.35), (cx - width * 0.205, width * 0.22, height * 0.45), (cx + width * 0.205, width * 0.22, height * 0.45)]:
        d.polygon([(tx - tw / 2, top + height * 0.10), (tx, top), (tx + tw / 2, top + height * 0.10)], fill=roof, outline="#872b28")

    d.ellipse((width * 0.08, height * 0.75, width * 0.92, height * 1.02), fill="#49b955")
    for i in range(9):
        t = i / 8
        py = height * (0.80 + 0.15 * t)
        pw = width * (0.05 + 0.05 * t)
        px = cx + math.sin(t * math.pi * 2) * width * 0.02
        d.ellipse((px - pw, py - pw * 0.35, px + pw, py + pw * 0.35), fill="#d8c7a2", outline="#8f7d62")

    for sx, sy, sr in [(0.18, 0.42, 0.04), (0.79, 0.38, 0.045), (0.66, 0.27, 0.03), (0.31, 0.30, 0.026)]:
        pts = star_points(sx * width, sy * height, sr * width, sr * width * 0.45)
        d.polygon(pts, fill="#ffd943", outline="#aa6e14")
    return img


def fit(base: Image.Image, size: tuple[int, int], x_bias: float = 0.5, y_bias: float = 0.45) -> Image.Image:
    return ImageOps.fit(base.convert("RGBA"), size, method=Image.Resampling.LANCZOS, centering=(x_bias, y_bias))


def title_overlay(img: Image.Image, title: str, subtitle: str = "", scale: float = 1.0, bottom: bool = False) -> Image.Image:
    img = img.convert("RGBA")
    d = ImageDraw.Draw(img)
    w, h = img.size
    fs = max(24, int(min(w, h) * 0.16 * scale))
    title_font = font(fs)
    sub_font = font(max(14, int(fs * 0.23)))
    box = d.textbbox((0, 0), title, font=title_font, stroke_width=max(2, fs // 18))
    tx = (w - (box[2] - box[0])) / 2
    ty = h * (0.62 if bottom else 0.10)
    pad = fs * 0.30
    d.rounded_rectangle((tx - pad, ty - pad * 0.35, tx + (box[2] - box[0]) + pad, ty + (box[3] - box[1]) + pad * 0.6), radius=int(fs * 0.14), fill=(24, 38, 82, 150))
    d.text((tx + fs * 0.04, ty + fs * 0.05), title, font=title_font, fill=(30, 30, 60, 160), stroke_width=max(2, fs // 18), stroke_fill=(30, 30, 60, 160))
    d.text((tx, ty), title, font=title_font, fill=(255, 226, 66, 255), stroke_width=max(2, fs // 18), stroke_fill=(91, 46, 122, 255))
    if subtitle:
        sb = d.textbbox((0, 0), subtitle, font=sub_font)
        sx = (w - (sb[2] - sb[0])) / 2
        sy = ty + (box[3] - box[1]) + fs * 0.16
        d.text((sx, sy), subtitle, font=sub_font, fill=(255, 255, 255, 245), stroke_width=max(1, fs // 45), stroke_fill=(46, 53, 90, 230))
    return img


def make_logo(title: str, subtitle: str) -> Image.Image:
    img = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    title_font = font(190 if len(title) <= 8 else max(86, int(1280 / max(8, len(title)) * 1.15)))
    box = d.textbbox((0, 0), title, font=title_font, stroke_width=10)
    tx = (1280 - (box[2] - box[0])) / 2
    ty = 240
    d.text((tx + 10, ty + 12), title, font=title_font, fill=(34, 32, 75, 150), stroke_width=10, stroke_fill=(34, 32, 75, 150))
    d.text((tx, ty), title, font=title_font, fill=(255, 226, 66, 255), stroke_width=10, stroke_fill=(91, 46, 122, 255))
    if subtitle:
        sub_font = font(42)
        sb = d.textbbox((0, 0), subtitle, font=sub_font, stroke_width=3)
        sx = (1280 - (sb[2] - sb[0])) / 2
        sy = ty + (box[3] - box[1]) + 24
        d.rounded_rectangle((sx - 26, sy - 10, sx + (sb[2] - sb[0]) + 26, sy + (sb[3] - sb[1]) + 16), radius=18, fill=(20, 120, 126, 230))
        d.text((sx, sy), subtitle, font=sub_font, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(20, 55, 80, 230))
    return img


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--base", default=None, help="Optional base image to crop into Steam assets")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = Image.open(args.base).convert("RGBA") if args.base else generic_scene(2400, 1400, slug(args.title))

    assets = {
        "poster.png": title_overlay(fit(base, (600, 900)), args.title, args.subtitle, 1.0, False),
        "capsule.png": title_overlay(fit(base, (920, 430)), args.title, "", 0.70, False),
        "hero.png": title_overlay(fit(base, (1920, 620), 0.50, 0.36), args.title, "", 0.55, False),
        "library_hero.png": title_overlay(fit(base, (3840, 1240), 0.50, 0.36), args.title, "", 0.55, False),
        "logo.png": make_logo(args.title, args.subtitle),
        "icon.png": title_overlay(fit(base, (512, 512)), args.title, "", 0.72, True),
    }
    for name, image in assets.items():
        image.save(out / name)
        print(out / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
