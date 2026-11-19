"""Builds the landing page's social card and favicons (macOS, needs Google Chrome).

  site/og.jpg                1200×630 Open Graph / Twitter card (< 500 KB for WhatsApp)
  site/favicon.ico           16/32/48 px, for Google Search and old browsers
  site/favicon-32x32.png     PNG favicon
  site/apple-touch-icon.png  180×180, opaque, for iOS home screens

Run after desktop/icon/make_icon.py:
  backend/.venv/bin/python desktop/make_web_assets.py
"""
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ICON = ROOT / "desktop" / "icon" / "icon.png"  # 1024 px app icon (transparent corners)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def chrome_shot(url: str, out: Path, w: int, h: int, scale: int = 1) -> None:
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
         f"--force-device-scale-factor={scale}", f"--window-size={w},{h}", f"--screenshot={out}", url],
        check=True, capture_output=True,
    )


def sips(*args: str) -> None:
    subprocess.run(["sips", *args], check=True, capture_output=True)


def write_ico(sources: list[Path], out: Path) -> None:
    datas = [p.read_bytes() for p in sources]
    sizes = [int(subprocess.run(["sips", "-g", "pixelWidth", str(p)], capture_output=True, text=True)
                 .stdout.split()[-1]) for p in sources]
    header = struct.pack("<HHH", 0, 1, len(datas))
    offset = 6 + 16 * len(datas)
    entries = b""
    for px, data in zip(sizes, datas):
        entries += struct.pack("<BBBBHHII", px % 256, px % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out.write_bytes(header + entries + b"".join(datas))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # Social card: render at 1x, then JPEG keeps it far under WhatsApp's 500 KB limit.
        png = tmp / "og.png"
        chrome_shot((SITE / "og" / "card.html").as_uri(), png, 1200, 630)
        sips("-s", "format", "jpeg", "-s", "formatOptions", "85", str(png), "--out", str(SITE / "og.jpg"))

        # Favicons from the app icon. The icon has a transparent margin (macOS
        # grid), so crop to the tile first: it reads bigger at 16–32 px.
        tile = tmp / "tile.png"
        sips("-c", "840", "840", str(ICON), "--out", str(tile))
        pngs = []
        for px in (16, 32, 48):
            p = tmp / f"{px}.png"
            sips("-z", str(px), str(px), str(tile), "--out", str(p))
            pngs.append(p)
        write_ico(pngs, SITE / "favicon.ico")
        (SITE / "favicon-32x32.png").write_bytes(pngs[1].read_bytes())

        # iOS rounds the corners itself and wants an opaque square, so draw the
        # full-bleed tile background behind the mark.
        touch = tmp / "touch.html"
        touch.write_text(
            '<html><body style="margin:0;width:180px;height:180px;'
            'background:linear-gradient(#262838,#121320);display:grid;place-items:center">'
            f'<img src="{(SITE / "assets" / "mark.svg").as_uri()}" style="width:132px"></body></html>'
        )
        apple = tmp / "apple.png"
        chrome_shot(touch.as_uri(), apple, 180, 180)
        sips("-s", "format", "png", str(apple), "--out", str(SITE / "apple-touch-icon.png"))

    for name in ("og.jpg", "favicon.ico", "favicon-32x32.png", "apple-touch-icon.png"):
        f = SITE / name
        print(f"{name:24} {f.stat().st_size / 1024:6.1f} KB")
