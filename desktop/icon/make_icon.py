"""Draws the app icon (1024px PNG) with numpy only, then builds Stemmer.icns.

Run: backend/.venv/bin/python desktop/icon/make_icon.py
"""
import struct
import subprocess
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
N = 1024
STEMS = ["#8b7dff", "#ff5c84", "#f4f000", "#2dff9a"]  # vocals, drums, bass, other


def rgb(hex_: str) -> np.ndarray:
    return np.array([int(hex_[i:i + 2], 16) for i in (1, 3, 5)], float)


def rounded_mask(x0, y0, x1, y1, r, yy, xx):
    cx = np.clip(xx, x0 + r, x1 - r)
    cy = np.clip(yy, y0 + r, y1 - r)
    d = np.hypot(xx - cx, yy - cy)
    return np.clip(r - d + 0.5, 0, 1) * ((xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1))


def draw() -> np.ndarray:
    yy, xx = np.mgrid[0:N, 0:N].astype(float)
    img = np.zeros((N, N, 4))
    # macOS icon grid: ~824px tile centred on the 1024 canvas.
    m, r = 100, 185
    tile = rounded_mask(m, m, N - m, N - m, r, yy, xx)
    shade = 1 - (yy - m) / (N - 2 * m) * 0.35
    img[..., :3] = (rgb("#262833") * shade[..., None])
    img[..., 3] = tile

    rng = np.random.default_rng(7)
    lane_h, top, left, right = 130, 250, 210, N - 210
    for i, color in enumerate(STEMS):
        cy = top + i * (lane_h + 20) + lane_h / 2
        cols = np.arange(left, right, 14)
        env = 0.35 + 0.65 * np.abs(np.sin(cols / (60 + i * 25) + i))
        amp = env * rng.uniform(0.45, 1.0, len(cols)) * lane_h / 2
        bar = np.zeros((N, N))
        for x, a in zip(cols, amp):
            bar = np.maximum(bar, rounded_mask(x, cy - a, x + 8, cy + a, 4, yy, xx))
        bar *= tile
        img[..., :3] = img[..., :3] * (1 - bar[..., None]) + rgb(color) * bar[..., None]
    img[..., :3] = np.clip(img[..., :3], 0, 255)
    img[..., 3] *= 255
    return img.astype(np.uint8)


def write_png(path: Path, rgba: np.ndarray) -> None:
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    png = HERE / "icon.png"
    write_png(png, draw())
    iconset = HERE / "Stemmer.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            px = size * scale
            subprocess.run(["sips", "-z", str(px), str(px), str(png), "--out", str(iconset / name)],
                           check=True, capture_output=True)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "Stemmer.icns")], check=True)
    print("wrote", HERE / "Stemmer.icns")
