"""Tempo and time-signature estimation with librosa.

Both come from the drums stem, which is far cleaner than the full mix.

Tempo: find the strongest pulse, pick the right octave of it, beat-track at
that tempo, then fit a line through the beat times for an exact BPM.

Time signature: describe each beat by its rhythm (onset strength in 4 bands
x 4 sub-beat slots), then check whether that pattern repeats every 3 beats
or every 4. It can't tell 3/4 from 6/8, so treat it as an estimate.
"""
from pathlib import Path

import librosa
import numpy as np

SR = 22050
MEL_BANDS = [0, 8, 24, 64, 128]  # edges of 4 bands: kick, low-mid, snare, cymbals
SLOTS = 4                         # sub-beat resolution of each beat's pattern


def _load(path: Path) -> np.ndarray:
    y, _ = librosa.load(path, sr=SR, mono=True)
    return y


def _pick_tempo(onset: np.ndarray) -> float:
    """Pick the pulse whose octave family (itself, half and double) is
    strongest, then the member of that family closest to 120 BPM.

    A song's real pulse shows up at several octaves, while side pulses (e.g.
    107 for a song at 80/160, a 4:3 cross-rhythm) usually stand alone. Scoring
    families instead of single peaks keeps a strong side pulse from winning,
    and avoids librosa's default 120 BPM prior pulling onto one.
    """
    tg = librosa.feature.tempogram(onset_envelope=onset, sr=SR)
    strength = tg.mean(axis=1)
    bpms = librosa.tempo_frequencies(len(strength), sr=SR)
    ok = np.isfinite(bpms) & (bpms > 20) & (bpms < 500)
    bpms, strength = bpms[ok][::-1], strength[ok][::-1]  # ascending BPM

    def at(bpm: float) -> float:
        return float(np.interp(bpm, bpms, strength)) if bpms[0] <= bpm <= bpms[-1] else 0.0

    peaks = [
        bpms[i] for i in range(1, len(bpms) - 1)
        if strength[i] >= strength[i - 1] and strength[i] >= strength[i + 1] and 40 <= bpms[i] <= 240
    ]
    if not peaks:
        return 120.0
    root = max(peaks, key=lambda t: at(t) + 0.5 * (at(t * 2) + at(t / 2)))
    family = [root * f for f in (0.5, 1, 2) if 60 <= root * f <= 200] or [root]
    return float(min(family, key=lambda b: abs(np.log2(b / 120))))


def _beat_patterns(bands: np.ndarray, beats: np.ndarray) -> np.ndarray:
    """One normalised rhythm vector per beat: bands x sub-beat slots."""
    rows = []
    for start, end in zip(beats[:-1], beats[1:]):
        edges = np.linspace(start, end, SLOTS + 1).astype(int)
        rows.append([
            bands[b, edges[s]:max(edges[s + 1], edges[s] + 1)].max()
            for b in range(bands.shape[0]) for s in range(SLOTS)
        ])
    patterns = np.array(rows)
    patterns -= patterns.mean(axis=0)
    patterns /= np.linalg.norm(patterns, axis=1, keepdims=True) + 1e-9
    return patterns


def _repeat(patterns: np.ndarray, lag: int) -> float:
    """Average similarity between each beat and the beat `lag` later."""
    return float(np.mean(np.sum(patterns[:-lag] * patterns[lag:], axis=1)))


def analyze(mix: Path, drums: Path | None) -> dict:
    y_drums = _load(drums) if drums else None
    # A near-silent drum stem (ballads, solo piano) gives no beats; use the mix.
    use_drums = y_drums is not None and np.sqrt(np.mean(y_drums**2)) > 0.01
    y = y_drums if use_drums else _load(mix)
    source = "drums" if use_drums else "mix"

    bands = librosa.onset.onset_strength_multi(y=y, sr=SR, channels=MEL_BANDS)
    onset = bands.sum(axis=0)
    _, beats = librosa.beat.beat_track(onset_envelope=onset, sr=SR, bpm=_pick_tempo(onset))
    if len(beats) < 24:
        return {"bpm": None, "time_signature": None, "source": source}

    # librosa's tempo is quantised to a coarse grid; fitting a line through
    # the tracked beat times gives the actual beat period.
    times = librosa.frames_to_time(beats, sr=SR)
    bpm = float(60 / np.polyfit(np.arange(len(times)), times, 1)[0])

    patterns = _beat_patterns(bands, beats)
    triple = (_repeat(patterns, 3) + _repeat(patterns, 6)) / 2
    quad = (_repeat(patterns, 4) + _repeat(patterns, 8)) / 2
    # 4/4 is far more common, so 3/4 has to win clearly.
    meter = 3 if triple > quad + 0.05 else 4

    return {"bpm": round(bpm, 1), "time_signature": f"{meter}/4", "source": source}
