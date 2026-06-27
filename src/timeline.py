"""Offline toneart-tidslinje: vindue-detektioner -> segmenter -> opslag.

segment_windows er REN (ingen DSP) og fuldt testbar. analyze_timeline kobler
detektion (key_detection.detect_key) paa toppen via dependency-injection."""
from collections import defaultdict
from dataclasses import dataclass, replace

from key_detection import detect_key


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


def global_pc(windows):
    """Sangens dominerende toneart: pc med mest confident varighed."""
    score = defaultdict(float)
    for w in windows:
        if w.relative_major_pc is not None:
            score[w.relative_major_pc] += w.confidence
    return max(score, key=score.get) if score else None


def consolidate_related(windows, dominance_threshold=0.6):
    """Kollaps I/IV/V-forvekslinger til sangens globale toneart — MEN kun naar én
    toneart klart dominerer hele sporet.

    Korte vinduer fanger den aktuelle akkord (tonika/subdominant/dominant), ikke
    sangens toneart -> en ét-toneart-sang laeses som beslægtede keys {global,
    global+5, global+7} (I/IV/V relmaj). Hvis global dominerer >= tærskel er de
    øvrige misreads -> saet dem = global.

    Hvis INGEN toneart dominerer (to ca. lige store centre, fx vers i D + omkvæd i
    A) er det en ÆGTE modulation -> roer ikke vinduerne. Det forhindrer at en
    D<->A-modulation (A = D+7) fejlagtigt kollapses."""
    g = global_pc(windows)
    if g is None:
        return windows
    confident = [w.relative_major_pc for w in windows if w.relative_major_pc is not None]
    if not confident:
        return windows
    ratio = sum(1 for pc in confident if pc == g) / len(confident)
    if ratio < dominance_threshold:
        return windows  # ingen klar global -> behandl som ægte fler-toneart
    close = {g, (g + 5) % 12, (g + 7) % 12}
    out = []
    for w in windows:
        if w.relative_major_pc in close and w.relative_major_pc != g:
            w = replace(w, relative_major_pc=g)
        out.append(w)
    return out


def detect_windows(samples, sr, *, window_seconds, hop_seconds, conf_threshold, detect=detect_key):
    """Glidende key-detektion -> liste af WindowKey (rå, ingen udglatning)."""
    win = int(window_seconds * sr)
    hop = int(hop_seconds * sr)
    windows = []
    pos = 0
    while pos + win <= len(samples) or (pos < len(samples) and not windows):
        seg = samples[pos:pos + win]
        if len(seg) < win // 2:
            break
        res = detect(seg, sr)
        pc = res.relative_major_pc if res.confidence >= conf_threshold else None
        windows.append(WindowKey(t=pos / sr, relative_major_pc=pc,
                                 key=res.key, mode=res.mode, confidence=res.confidence))
        pos += hop
    return windows


def analyze_timeline(samples, sr, *, window_seconds, hop_seconds,
                     min_segment_seconds, conf_threshold, detect=detect_key,
                     consolidate=True, dominance_threshold=0.6):
    windows = detect_windows(samples, sr, window_seconds=window_seconds,
                             hop_seconds=hop_seconds, conf_threshold=conf_threshold, detect=detect)
    if consolidate:
        windows = consolidate_related(windows, dominance_threshold)
    return segment_windows(windows, hop_seconds, min_segment_seconds)


class Timeline:
    def __init__(self, segments):
        self.segments = segments

    def lookup(self, t):
        if not self.segments:
            return None
        for s in self.segments:
            if s.start <= t < s.end:
                return s
        return self.segments[0] if t < self.segments[0].start else self.segments[-1]
