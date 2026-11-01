# Third-party notices

The Stemmer source code in this repository is MIT licensed (see `LICENSE`). The packaged app (`Stemmer.app` / the `.dmg` on the Releases page) also bundles the components below, each under its own license.

## Components with copyleft licenses

### FFmpeg (GPL)
The app bundles an FFmpeg executable from [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) 0.6.0 (`ffmpeg-macos-aarch64-v7.1`). That build is configured with `--enable-gpl` and is licensed under the GNU General Public License v2 or later. Stemmer runs it as a separate program and doesn't link to it.

- FFmpeg source code: https://ffmpeg.org/download.html (release 7.1)
- Build scripts for this binary: https://github.com/imageio/imageio-binaries
- License text: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html

### lameenc / LAME (LGPL-3.0)
Used to encode stems to MP3. Source: https://github.com/chrisstaite/lameenc and https://lame.sourceforge.io. It's included as a separate, replaceable Python extension module inside the app bundle.

## Model weights

Demucs pretrained models `htdemucs` and `htdemucs_6s` by Meta Platforms, Inc., MIT License. https://github.com/facebookresearch/demucs

## Permissive licenses

| Component | License |
|---|---|
| Demucs | MIT |
| PyTorch, torchaudio | BSD-3-Clause |
| librosa | ISC |
| NumPy, SciPy, Numba | BSD-3-Clause / BSD |
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| soundfile | BSD-3-Clause |
| pywebview | BSD-3-Clause |
| imageio-ffmpeg (Python wrapper) | BSD-2-Clause |
| PyInstaller bootloader | GPL-2.0 with an exception that allows bundling apps under any license |

Inside the app bundle, the license file of each main Python package is in `Stemmer.app/Contents/Resources/<package>.dist-info/`. This file and Stemmer's `LICENSE` are in `Stemmer.app/Contents/Resources/`.
