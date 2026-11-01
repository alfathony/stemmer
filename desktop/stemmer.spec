# PyInstaller build for Stemmer.app. Use build_mac.sh rather than running this directly.
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
MODELS = Path(os.environ.get("STEMMER_MODELS", Path.home() / ".cache/torch/hub/checkpoints"))

datas = [
    (str(ROOT / "frontend" / "dist"), "frontend"),
    # Demucs weights, laid out like torch's cache so TORCH_HOME can point here.
    *[(str(p), "models/hub/checkpoints") for p in MODELS.glob("*.th")],
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]
# Ship each bundled package's metadata, which carries its license file.
for dist in ["torch", "torchaudio", "numpy", "scipy", "numba", "llvmlite", "librosa", "demucs",
             "fastapi", "starlette", "uvicorn", "pydantic", "soundfile", "lameenc",
             "imageio-ffmpeg", "pywebview", "pyobjc-core"]:
    datas += copy_metadata(dist)
binaries = []
hiddenimports = collect_submodules("uvicorn")

# Packages that load data files, plugins or native libs at runtime.
for pkg in ["demucs", "librosa", "lameenc", "imageio_ffmpeg", "webview", "soundfile", "soxr"]:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(ROOT / "desktop" / "stemmer_app.py")],
    pathex=[str(ROOT / "backend")],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports + ["app", "analysis", "separator"],
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    # numba's on-disk cache (used by librosa) needs real .py files next to
    # the compiled ones, not just the zipped bytecode.
    module_collection_mode={"librosa": "pyz+py"},
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Stemmer",
    console=False,
    target_arch="arm64",
)
coll = COLLECT(exe, a.binaries, a.datas, name="Stemmer")
app = BUNDLE(
    coll,
    name="Stemmer.app",
    icon=str(ROOT / "desktop" / "icon" / "Stemmer.icns"),
    bundle_identifier="app.stemmer.desktop",
    info_plist={
        "CFBundleDisplayName": "Stemmer",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    },
)
