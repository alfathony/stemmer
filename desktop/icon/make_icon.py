"""Draws the Stemmer logo and builds every icon from it.

The mark: one white waveform that splits into four coloured stems
(vocals, drums, bass, other), which is what the app does.

Outputs:
  desktop/icon/logo.svg         app icon (macOS-style tile), master artwork
  desktop/icon/mark.svg         the mark alone on transparent, for UI and web
  desktop/icon/icon.png         1024 px render of logo.svg
  desktop/icon/Stemmer.icns     macOS
  desktop/icon/Stemmer.ico      Windows
  frontend/public/favicon.svg   app UI favicon / header mark
  site/assets/{logo,mark}.svg   landing page

Run (macOS, needs Google Chrome for rendering):
  backend/.venv/bin/python desktop/icon/make_icon.py
"""
import math
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

STEMS = ["#8B7DFF", "#FF5C84", "#F7E35A", "#2DE39A"]  # vocals, drums, bass, other


def wave_points(x0, x1, y_at, amp_at, cycles, steps=160):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        x = x0 + (x1 - x0) * t
        pts.append((x, y_at(t) + amp_at(t) * math.sin(t * cycles * 2 * math.pi)))
    return pts


def path(pts):
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def mark_paths(cx=512, cy=512, scale=1.0):
    """Stroke paths for the mark, in a 1024 box centred on (cx, cy)."""
    s = scale
    split_x = cx - 40 * s
    left_x0, right_x1 = cx - 340 * s, cx + 330 * s

    def ease(t):  # smooth S-curve for the fan-out
        return t * t * (3 - 2 * t)

    # Incoming mix: one waveform that swells and narrows to the split point.
    mix = wave_points(
        left_x0, split_x,
        y_at=lambda t: cy,
        amp_at=lambda t: 120 * s * math.sin(math.pi * t) ** 1.4,
        cycles=3,
    )
    stems = []
    for k in (-1.5, -0.5, 0.5, 1.5):
        end_y = cy + k * 112 * s
        stems.append(wave_points(
            split_x, right_x1,
            y_at=lambda t, end_y=end_y: cy + (end_y - cy) * ease(min(1, t * 1.9)),
            # Ripple starts once the strands have separated, in phase so they
            # read as a tidy bundle.
            amp_at=lambda t: 24 * s * ease(min(1, max(0, (t - 0.35) * 2.2))),
            cycles=3,
        ))
    return path(mix), [path(p) for p in stems]


def mark_svg(stroke_scale=1.0, size=1024, tile=False):
    mix, stems = mark_paths(scale=0.86 if tile else 1.0)
    w_mix, w_stem = 30 * stroke_scale, 28 * stroke_scale
    defs = """
  <defs>
    <linearGradient id="tile" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#262838"/>
      <stop offset="1" stop-color="#121320"/>
    </linearGradient>
    <linearGradient id="edge" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity=".16"/>
      <stop offset=".5" stop-color="#ffffff" stop-opacity=".03"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity=".08"/>
    </linearGradient>
    <linearGradient id="mixfade" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#ffffff" stop-opacity=".55"/>
      <stop offset="1" stop-color="#ffffff"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="9" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>"""
    body = ""
    if tile:
        # macOS icon grid: 824 px rounded tile centred on a 1024 canvas.
        body += '\n  <rect x="100" y="100" width="824" height="824" rx="185" fill="url(#tile)"/>'
        body += '\n  <rect x="101.5" y="101.5" width="821" height="821" rx="183.5" fill="none" stroke="url(#edge)" stroke-width="3"/>'
    stems_svg = "\n    ".join(
        f'<path d="{d}" stroke="{c}" stroke-width="{w_stem:.0f}"/>' for d, c in zip(stems, STEMS)
    )
    body += f"""
  <g fill="none" stroke-linecap="round" stroke-linejoin="round">
    <g{' filter="url(#glow)"' if tile else ''}>
    {stems_svg}
    </g>
    <path d="{mix}" stroke="url(#mixfade)" stroke-width="{w_mix:.0f}"/>
  </g>"""
    # The bare mark is cropped tight to the artwork so it stays legible small.
    box = "0 0 1024 1024" if tile else "140 270 744 484"
    w, h = (size, size) if tile else (size, round(size * 484 / 744))
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box}" width="{w}" height="{h}">{defs}{body}\n</svg>\n'


def render_png(svg: Path, out: Path, px: int = 1024) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "r.html"
        html.write_text(
            f'<html><body style="margin:0;background:transparent">'
            f'<img src="{svg.resolve().as_uri()}" width="{px}" height="{px}" style="display:block"></body></html>'
        )
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--default-background-color=00000000", "--force-device-scale-factor=1",
             f"--window-size={px},{px}", f"--screenshot={out}", html.as_uri()],
            check=True, capture_output=True,
        )


def write_ico(png: Path, out: Path) -> None:
    """Windows .ico with PNG-compressed entries (read natively since Vista)."""
    sizes = [16, 24, 32, 48, 64, 128, 256]
    with tempfile.TemporaryDirectory() as tmp:
        datas = []
        for px in sizes:
            p = Path(tmp) / f"{px}.png"
            subprocess.run(["sips", "-z", str(px), str(px), str(png), "--out", str(p)],
                           check=True, capture_output=True)
            datas.append(p.read_bytes())
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for px, data in zip(sizes, datas):
        entries += struct.pack("<BBBBHHII", px % 256, px % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out.write_bytes(header + entries + b"".join(datas))


def write_icns(png: Path, out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "Stemmer.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = size * scale
                name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
                subprocess.run(["sips", "-z", str(px), str(px), str(png), "--out", str(iconset / name)],
                               check=True, capture_output=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)


if __name__ == "__main__":
    logo, mark = HERE / "logo.svg", HERE / "mark.svg"
    logo.write_text(mark_svg(tile=True))
    mark.write_text(mark_svg(stroke_scale=1.7, size=64))
    png = HERE / "icon.png"
    render_png(logo, png)
    write_icns(png, HERE / "Stemmer.icns")
    write_ico(png, HERE / "Stemmer.ico")
    for dest in [ROOT / "frontend" / "public" / "favicon.svg", ROOT / "site" / "assets" / "mark.svg"]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mark, dest)
    (ROOT / "site" / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(logo, ROOT / "site" / "assets" / "logo.svg")
    print("wrote", logo, mark, png, "Stemmer.icns", "Stemmer.ico")
