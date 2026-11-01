"""Desktop launcher: runs the Stemmer backend locally and shows the UI in a
native window (WKWebView on macOS, WebView2 on Windows).

Dev run (from the repo root, after `npm run build` in frontend/):
    backend/.venv/bin/python desktop/stemmer_app.py
"""
import multiprocessing
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
# PyInstaller unpacks bundled files here; in dev, use the repo layout.
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def support_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = base / "Stemmer"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_streams() -> None:
    """Windowed apps can start with no stdout/stderr; Demucs and tqdm need them."""
    for name, fd in (("stdout", 1), ("stderr", 2)):
        if getattr(sys, name) is None:
            try:
                setattr(sys, name, open(fd, "w", closefd=False))
            except OSError:
                setattr(sys, name, open(os.devnull, "w"))


def setup_env(support: Path) -> None:
    os.environ["STEMMER_DATA_DIR"] = str(support / "data")
    os.environ.setdefault("NUMBA_CACHE_DIR", str(support / "numba-cache"))

    ui = BUNDLE / "frontend" if FROZEN else BUNDLE / "frontend" / "dist"
    os.environ["STEMMER_STATIC_DIR"] = str(ui)

    # Models shipped inside the app, laid out like torch's cache.
    models = BUNDLE / "models"
    if (models / "hub" / "checkpoints").is_dir():
        os.environ["TORCH_HOME"] = str(models)

    # Apps launched from Finder don't get Homebrew on PATH, so expose the
    # bundled ffmpeg as plain `ffmpeg` for both our code and Demucs.
    import imageio_ffmpeg

    bin_dir = support / "bin"
    bin_dir.mkdir(exist_ok=True)
    link = bin_dir / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    target = imageio_ffmpeg.get_ffmpeg_exe()
    if not link.exists() or os.path.realpath(link) != os.path.realpath(target):
        link.unlink(missing_ok=True)
        try:
            link.symlink_to(target)
        except OSError:  # Windows without symlink rights
            import shutil

            shutil.copy2(target, link)
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until_up(url: str, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"backend did not start at {url}")


class Api:
    """Exposed to the page as window.pywebview.api."""

    def choose_save_path(self, filename: str) -> str | None:
        import webview

        from app import approved_save_paths

        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG, directory=str(Path.home() / "Downloads"), save_filename=filename,
        )
        path = result[0] if isinstance(result, (list, tuple)) else result
        if not path:
            return None
        approved_save_paths.add(path)
        return path


def run_demucs(args: list[str]) -> None:
    ensure_streams()
    from demucs.separate import main

    main(args)


def run_app() -> None:
    support = support_dir()
    if FROZEN:
        # No terminal for a Finder-launched app; keep a log for debugging.
        log = open(support / "stemmer.log", "a", buffering=1)
        sys.stdout = sys.stderr = log
    setup_env(support)
    if not FROZEN:
        sys.path.insert(0, str(BUNDLE / "backend"))

    import uvicorn
    import webview

    from app import app

    port = int(os.environ.get("STEMMER_PORT") or free_port())
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    wait_until_up(url)
    print(f"Stemmer running at {url}", flush=True)

    webview.create_window(
        "Stemmer", url,
        width=1200, height=860, min_size=(720, 560),
        background_color="#16171C",
        js_api=Api(),
    )
    webview.start()
    server.should_exit = True


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--demucs":
        run_demucs(sys.argv[2:])
    else:
        run_app()
