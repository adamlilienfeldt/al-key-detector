"""Offline toneart-tidslinje: vindue-detektioner -> segmenter -> opslag.

segment_windows er REN (ingen DSP) og fuldt testbar. analyze_timeline kobler
detektion (key_detection.detect_key) paa toppen via dependency-injection."""
from dataclasses import dataclass


@dataclass
class WindowKey:
    t: float
    relative_major_pc: int | None
    key: str
    mode: str
    confidence: float


@dataclass
class Segment:
    start: float
    end: float
    relative_major_pc: int | None
    key: str
    mode: str
    confidence: float


def _median_filter_pc(pcs, k=3):
    """Median-glat pc-sekvens (k ulige). None bevares som None."""
    out = []
    half = k // 2
    for i in range(len(pcs)):
        window = [pcs[j] for j in range(max(0, i - half), min(len(pcs), i + half + 1))
                  if pcs[j] is not None]
        if not window:
            out.append(None)
        else:
            window.sort()
            out.append(window[len(window) // 2])
    return out


def segment_windows(windows, hop, min_segment_seconds):
    """Slaa vinduer med samme pc sammen til segmenter. Korte runs (< min_segment_seconds)
    absorberes i nabo via median-glatning. None-pc (lav conf) arver naboens pc."""
    if not windows:
        return []
    raw = [w.relative_major_pc for w in windows]
    smooth = _median_filter_pc(raw, k=max(3, int(round(min_segment_seconds / hop)) | 1))
    # forward-fill None med sidste kendte pc (eller naeste hvis i starten)
    filled = list(smooth)
    last = None
    for i in range(len(filled)):
        if filled[i] is None:
            filled[i] = last
        else:
            last = filled[i]
    nxt = None
    for i in range(len(filled) - 1, -1, -1):
        if filled[i] is None:
            filled[i] = nxt
        else:
            nxt = filled[i]
    segs = []
    for i, w in enumerate(windows):
        pc = filled[i]
        if segs and segs[-1].relative_major_pc == pc:
            segs[-1].end = w.t + hop
            if w.confidence > segs[-1].confidence:
                segs[-1].key, segs[-1].mode, segs[-1].confidence = w.key, w.mode, w.confidence
        else:
            segs.append(Segment(start=w.t, end=w.t + hop, relative_major_pc=pc,
                                key=w.key, mode=w.mode, confidence=w.confidence))
    return segs
