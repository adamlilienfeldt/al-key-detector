"""Fase 1 — chroma-baseret key-detection via Krumhansl-Schmuckler profil-matching.

detect_key(samples, sr) -> KeyResult(key, mode, confidence, relative_major)

Algoritme:
1. Beregn chromagram (CENS — robust mod timbre/dynamik) -> 12-dim pitch-class vektor.
2. Korreller (Pearson) mod 24 roterede K-S major/minor profiler.
3. Bedste korrelation = toneart. Confidence = top-korrelation, margin = top minus næstbedste.

Relativ-major: scale droppes i MIDI (se projekt-beslutning) — minor mappes til
relativ major (root + 3 semitoner). detect_key returnerer den allerede beregnet.
"""
from dataclasses import dataclass
import numpy as np
import librosa

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Kessler nøgle-profiler (major / minor), normaliseret ved brug.
_KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


@dataclass
class KeyResult:
    key: str            # fx "A"
    mode: str           # "major" | "minor"
    pitch_class: int    # 0..11 (root)
    confidence: float   # top korrelation 0..1
    margin: float       # top minus næstbedste (stabilitets-indikator)
    relative_major_pc: int  # pitch-class til major-tonen vi sender via CC#16

    def __str__(self):
        return (f"{self.key} {self.mode} (relmaj={NOTE_NAMES[self.relative_major_pc]}, "
                f"conf={self.confidence:.2f}, margin={self.margin:.2f})")


def _normalize(v):
    v = v - v.mean()
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


_PROFILES = []  # liste af (pitch_class, mode, normaliseret-profil)
for pc in range(12):
    _PROFILES.append((pc, "major", _normalize(np.roll(_KS_MAJOR, pc))))
    _PROFILES.append((pc, "minor", _normalize(np.roll(_KS_MINOR, pc))))


def chroma_vector(samples, sr):
    """Mono float -> 12-dim gennemsnitlig chroma (CENS)."""
    y = samples if samples.ndim == 1 else samples.mean(axis=1)
    y = np.asarray(y, dtype=np.float32)
    chroma = librosa.feature.chroma_cens(y=y, sr=sr)
    return chroma.mean(axis=1)


def detect_key(samples, sr):
    vec = _normalize(chroma_vector(samples, sr))
    scored = [(pc, mode, float(np.dot(vec, prof))) for pc, mode, prof in _PROFILES]
    scored.sort(key=lambda t: t[2], reverse=True)
    pc, mode, corr = scored[0]
    margin = corr - scored[1][2]
    rel_major_pc = pc if mode == "major" else (pc + 3) % 12
    return KeyResult(
        key=NOTE_NAMES[pc], mode=mode, pitch_class=pc,
        confidence=max(0.0, corr), margin=margin, relative_major_pc=rel_major_pc,
    )


if __name__ == "__main__":
    import sys
    from scipy.io import wavfile
    if len(sys.argv) < 2:
        print("Brug: key_detection.py <fil.wav> [fil2.wav ...]")
        raise SystemExit(1)
    for path in sys.argv[1:]:
        sr, data = wavfile.read(path)
        if data.dtype.kind in "iu":
            data = data.astype(np.float32) / np.iinfo(data.dtype).max
        res = detect_key(data, sr)
        print(f"{path}: {res}")
