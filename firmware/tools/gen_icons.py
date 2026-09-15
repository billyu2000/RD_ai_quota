#!/usr/bin/env python3
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "images"
OUT = ROOT / "firmware" / "src" / "icons.h"
SIZE = 32

SOURCES = [
    ("claude", IMAGES / "claude.png"),
    ("codex", IMAGES / "codex.jpg"),
    ("grok", IMAGES / "grok.jpg"),
    ("zai", IMAGES / "z.ai.jpg"),
]


def rgb565(r: int, g: int, b: int) -> int:
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def load_square(path: Path) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    pad = im.getpixel((0, 0))[:3] + (255,)
    bg = Image.new("RGBA", im.size, pad)
    im = Image.alpha_composite(bg, im).convert("RGB")
    w, h = im.size
    side = max(w, h)
    canvas = Image.new("RGB", (side, side), im.getpixel((0, 0)))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))
    resample = Image.Resampling.NEAREST if path.suffix.lower() == ".png" else Image.Resampling.LANCZOS
    return canvas.resize((SIZE, SIZE), resample)


def emit_array(name: str, im: Image.Image) -> str:
    pixels = []
    for y in range(SIZE):
        for x in range(SIZE):
            r, g, b = im.getpixel((x, y))
            pixels.append(rgb565(r, g, b))
    lines = [f"const uint16_t icon_{name}[{SIZE * SIZE}] PROGMEM = {{"]
    for i in range(0, len(pixels), 12):
        chunk = ", ".join(f"0x{v:04X}" for v in pixels[i : i + 12])
        comma = "," if i + 12 < len(pixels) else ""
        lines.append(f"  {chunk}{comma}")
    lines.append("};")
    return "\n".join(lines)


parts = [
    "#pragma once",
    "",
    "#include <Arduino.h>",
    "#include <pgmspace.h>",
    "",
    f"static const int ICON_SIZE = {SIZE};",
    "",
]
for name, path in SOURCES:
    parts.append(emit_array(name, load_square(path)))
    parts.append("")

OUT.write_text("\n".join(parts))
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
