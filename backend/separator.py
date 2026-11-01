"""Thin wrapper around the Demucs CLI that reports progress."""
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

MODELS = {
    "4stems": "htdemucs",     # vocals, drums, bass, other
    "6stems": "htdemucs_6s",  # + guitar, piano
}

_PERCENT = re.compile(r"(\d{1,3})%\|")
# Keep child processes from flashing a console window on Windows.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def pick_device() -> str:
    forced = os.environ.get("STEMMER_DEVICE")
    if forced:
        return forced
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def separate(
    src: Path,
    out_dir: Path,
    mode: str,
    on_progress: Callable[[float], None],
) -> dict[str, Path]:
    """Run Demucs on `src` and return {stem_name: mp3_path}."""
    device = pick_device()
    try:
        return _run(src, out_dir, MODELS[mode], device, on_progress)
    except RuntimeError:
        # Some Demucs layers aren't supported on Apple's MPS backend for certain
        # input lengths; the CPU always works, just slower.
        if device != "mps":
            raise
        on_progress(0.0)
        return _run(src, out_dir, MODELS[mode], "cpu", on_progress)


def _run(
    src: Path,
    out_dir: Path,
    model: str,
    device: str,
    on_progress: Callable[[float], None],
) -> dict[str, Path]:
    # Inside the packaged app there is no Python interpreter to run `-m demucs`;
    # the app binary runs Demucs itself when given --demucs (see desktop/).
    entry = ["--demucs"] if getattr(sys, "frozen", False) else ["-m", "demucs"]
    cmd = [
        sys.executable, *entry,
        "-n", model,
        "-d", device,
        "--mp3", "--mp3-bitrate", "256",
        "-o", str(out_dir),
        "--filename", "{stem}.{ext}",
        str(src),
    ]
    env = {**os.environ, "PYTORCH_ENABLE_MPS_FALLBACK": "1"}
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
        creationflags=NO_WINDOW,
    )

    # tqdm redraws with '\r', so read raw bytes and split on both separators.
    log, buf = [], b""
    assert proc.stdout is not None
    while chunk := proc.stdout.read(256):
        buf += chunk
        *lines, buf = re.split(rb"[\r\n]", buf)
        for raw in lines:
            line = raw.decode(errors="replace")
            log.append(line)
            if m := _PERCENT.search(line):
                on_progress(int(m.group(1)) / 100)
    if proc.wait() != 0:
        tail = "\n".join(l for l in log[-15:] if l.strip())
        raise RuntimeError(f"demucs failed:\n{tail}")

    stem_dir = out_dir / model
    stems = {p.stem: p for p in sorted(stem_dir.glob("*.mp3"))}
    if not stems:
        raise RuntimeError("demucs produced no stems")
    return stems
