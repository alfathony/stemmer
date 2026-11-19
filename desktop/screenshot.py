"""Takes the README/landing screenshot from the real app window (macOS).

Opens Stemmer in dev mode, loads a song in 6-stem mode as "Demo song.mp3",
seeks to ~37%, then saves a Retina PNG snapshot of the window's web view.

    npm --prefix frontend run build
    backend/.venv/bin/python desktop/screenshot.py path/to/song.mp3 docs/screenshot.png
"""
import base64
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "desktop"))
import stemmer_app  # noqa: E402
import webview  # noqa: E402

SONG, OUT = Path(sys.argv[1]), Path(sys.argv[2])
WIDTH, HEIGHT = 1440, 900


def drive(window):
    ev = window.evaluate_js

    def wait(expr, secs):
        end = time.time() + secs
        while time.time() < end:
            if ev(expr):
                return
            time.sleep(1)
        raise SystemExit(f"timed out waiting for {expr}")

    window.resize(WIDTH, HEIGHT)
    wait("document.readyState === 'complete'", 30)
    b64 = base64.b64encode(SONG.read_bytes()).decode()
    ev("""(() => { document.querySelector('input[value="6stems"]').checked = true;
      const b = Uint8Array.from(atob('%s'), c => c.charCodeAt(0));
      const dt = new DataTransfer(); dt.items.add(new File([b], 'Demo song.mp3', {type: 'audio/mpeg'}));
      document.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));
      return true; })()""" % b64)
    wait("!document.getElementById('mixer').hidden || !document.getElementById('progress-error').hidden", 900)
    ev("""(() => { const tl = document.getElementById('timeline'); const r = tl.getBoundingClientRect();
      const o = {clientX: r.left + r.width * 0.37, clientY: r.top + 60, bubbles: true, pointerId: 1};
      tl.dispatchEvent(new PointerEvent('pointerdown', o)); tl.dispatchEvent(new PointerEvent('pointerup', o));
      const s = document.querySelector('.strip input'); s.value = '1.15'; s.dispatchEvent(new Event('input'));
      return true; })()""")
    time.sleep(2)
    snapshot(window)
    window.destroy()


def snapshot(window):
    """Ask WKWebView itself for a Retina snapshot (no screen-recording permission needed)."""
    import AppKit
    import WebKit
    from PyObjCTools import AppHelper
    from webview.platforms.cocoa import BrowserView

    done = []

    def handler(image, error):
        if image is None:
            done.append(f"no image: {error}")
            return
        rep = AppKit.NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
        png = rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, None)
        png.writeToFile_atomically_(str(OUT), True)
        done.append(None)

    def take():
        wk = BrowserView.instances[window.uid].webview
        wk.takeSnapshotWithConfiguration_completionHandler_(WebKit.WKSnapshotConfiguration.alloc().init(), handler)

    AppHelper.callAfter(take)
    end = time.time() + 20
    while not done and time.time() < end:
        time.sleep(0.2)
    print("snapshot:", OUT, done or "timed out", flush=True)


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("STEMMER_PORT", "8790")
    real_start = webview.start
    webview.start = lambda *a, **k: real_start(drive, webview.windows[0])
    stemmer_app.run_app()
    # Retina snapshots are 2x; 2000 px wide is plenty for GitHub and the web.
    subprocess.run(["sips", "-Z", "2000", str(OUT)], check=True, capture_output=True)
