# YouTube Karaoke Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web app that plays a YouTube karaoke video, analyses the full track offline into a key timeline, and drives UAD Auto-Tune (MIDI CC#16/CC#18) from that timeline with look-ahead so mid-song modulations are followed with zero detection lag.

**Architecture:** Python async backend (FastAPI + uvicorn) serves a single-page frontend. Frontend embeds the YouTube IFrame player and streams playhead position over a websocket. Backend fetches audio (yt-dlp), builds a key timeline (reusing `key_detection.detect_key`), and on each position update looks up the key `lookahead` seconds ahead and sends MIDI. The existing passive live-detection system (`realtime.py`/`main.py`/`gui.py`) is untouched and remains as a fallback mode.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, websockets, yt-dlp, ffmpeg, librosa, numpy, mido (existing), YouTube IFrame Player API + Data API v3.

## Global Constraints

- Python: 3.11 (existing venv at `./venv`).
- Secrets: YouTube API key lives ONLY in `config.local.json` (gitignored). NEVER commit it. NEVER hardcode it in source.
- Reuse existing modules: `src/key_detection.py` (`detect_key(samples, sr) -> KeyResult`; `KeyResult` has `.pitch_class`, `.mode`, `.confidence`, `.margin`, `.relative_major_pc`, `.key`), `src/midi_output.py` (`open_port(match, _)`, `send_key(out, ch, cc, cc_map, pc)`, `load_cc_map() -> (dict, _)`), and `cc_key_map` from config.
- Do NOT modify `realtime.py`, `main.py`, `gui.py`, `smoothing.py` (fallback mode stays working).
- MIDI values: CC#16 = key (via `cc_key_map`), CC#18 = retune speed, `retune_sure`=0 (autotune ON), `retune_unsure`=127 (autotune OFF). From `config.json` → `midi`.
- All new run commands use `PYTHONPATH=src ./venv/bin/python ...`.
- Config: `analysis_samplerate` = 22050 (from `config.json` → `detection`).
- Tests: pytest. Run with `PYTHONPATH=src ./venv/bin/pytest`.

---

## File Structure

- Create `src/appconfig.py` — load+deep-merge `config.json` with `config.local.json`.
- Create `src/timeline.py` — `WindowKey`, `Segment`, `segment_windows(...)`, `analyze_timeline(...)`, `Timeline.lookup(t)`.
- Create `src/timeline_driver.py` — `MidiSink` (wraps midi_output), `TimelineDriver` (position → MIDI with look-ahead).
- Create `src/audio_fetch.py` — `fetch_audio(video_id, cache_dir) -> (samples, sr)` via yt-dlp + librosa, with cache.
- Create `src/youtube_search.py` — `search(query, api_key, max_results) -> list[dict]`.
- Create `src/server.py` — FastAPI app: static, `/api/search`, `/api/load`, `/api/timeline/{id}`, `/ws`.
- Create `src/web/index.html`, `src/web/app.js`, `src/web/style.css` — frontend.
- Create `tests/test_timeline.py`, `tests/test_timeline_driver.py`, `tests/test_audio_fetch.py`, `tests/test_appconfig.py`, `tests/test_server.py`.
- Modify `requirements.txt` — add deps.
- Modify `README.md` — document the new mode.

---

## Task 1: Dependencies + merged config loader

**Files:**
- Modify: `requirements.txt`
- Create: `src/appconfig.py`
- Test: `tests/test_appconfig.py`

**Interfaces:**
- Produces: `load_merged_config() -> dict` (deep-merges `config.local.json` over `config.json`); `get_cache_dir(cfg) -> str` (expanduser of `player.cache_dir`, created if missing).

- [ ] **Step 1: Add dependencies**

Append to `requirements.txt`:

```
fastapi
uvicorn[standard]
yt-dlp
```

- [ ] **Step 2: Install**

Run: `./venv/bin/pip install -r requirements.txt`
Expected: installs fastapi, uvicorn, yt-dlp (websockets comes with uvicorn[standard]).

- [ ] **Step 3: Write the failing test**

```python
# tests/test_appconfig.py
import json, os
from appconfig import load_merged_config, get_cache_dir

def _write(p, d):
    with open(p, "w") as f: json.dump(d, f)

def test_local_overrides_and_merges(tmp_path, monkeypatch):
    base = tmp_path / "config.json"; local = tmp_path / "config.local.json"
    _write(base, {"youtube": {"api_key": "", "search_max_results": 12}, "midi": {"cc_key": 16}})
    _write(local, {"youtube": {"api_key": "SECRET"}})
    monkeypatch.setattr("appconfig.CONFIG", str(base))
    monkeypatch.setattr("appconfig.CONFIG_LOCAL", str(local))
    cfg = load_merged_config()
    assert cfg["youtube"]["api_key"] == "SECRET"        # local wins
    assert cfg["youtube"]["search_max_results"] == 12     # base preserved
    assert cfg["midi"]["cc_key"] == 16                    # untouched section

def test_cache_dir_created(tmp_path):
    d = get_cache_dir({"player": {"cache_dir": str(tmp_path / "c")}})
    assert os.path.isdir(d)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_appconfig.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'appconfig'`

- [ ] **Step 5: Write minimal implementation**

```python
# src/appconfig.py
"""Merget config: config.json (committet) + config.local.json (gitignored secrets)."""
import json, os

CONFIG = os.path.join(os.path.dirname(__file__), "..", "config.json")
CONFIG_LOCAL = os.path.join(os.path.dirname(__file__), "..", "config.local.json")


def _deep_merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_merged_config():
    with open(CONFIG) as f:
        cfg = json.load(f)
    if os.path.exists(CONFIG_LOCAL):
        with open(CONFIG_LOCAL) as f:
            _deep_merge(cfg, json.load(f))
    return cfg


def get_cache_dir(cfg):
    d = os.path.expanduser(cfg.get("player", {}).get("cache_dir", "~/Library/Caches/AL_KEY_DETECTOR"))
    os.makedirs(d, exist_ok=True)
    return d
```

- [ ] **Step 6: Add config defaults to `config.json`**

Add these top-level keys to `config.json` (do NOT add `api_key` here — it stays in `config.local.json`):

```jsonc
  "youtube": { "search_max_results": 12 },
  "player": { "lookahead_seconds": 0.7, "cache_dir": "~/Library/Caches/AL_KEY_DETECTOR" },
  "timeline": { "window_seconds": 8, "hop_seconds": 1.0, "min_segment_seconds": 6, "conf_threshold": 0.40 }
```

- [ ] **Step 7: Run test to verify it passes**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_appconfig.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: Commit**

```bash
git add requirements.txt src/appconfig.py tests/test_appconfig.py config.json
git commit -m "feat: merged config loader (config.local.json secrets) + deps"
```

---

## Task 2: Pure window segmentation

**Files:**
- Create: `src/timeline.py`
- Test: `tests/test_timeline.py`

**Interfaces:**
- Produces:
  - `@dataclass WindowKey: t: float; relative_major_pc: int|None; key: str; mode: str; confidence: float`
  - `@dataclass Segment: start: float; end: float; relative_major_pc: int|None; key: str; mode: str; confidence: float`
  - `segment_windows(windows: list[WindowKey], hop: float, min_segment_seconds: float) -> list[Segment]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_timeline.py
from timeline import WindowKey, Segment, segment_windows

def W(t, pc, conf=0.7): return WindowKey(t=t, relative_major_pc=pc, key="X", mode="major", confidence=conf)

def test_single_key_one_segment():
    ws = [W(i*1.0, 0) for i in range(10)]
    segs = segment_windows(ws, hop=1.0, min_segment_seconds=3)
    assert len(segs) == 1
    assert segs[0].relative_major_pc == 0

def test_sustained_change_splits():
    ws = [W(i, 0) for i in range(8)] + [W(8+i, 7) for i in range(8)]   # C then G, each 8s
    segs = segment_windows(ws, hop=1.0, min_segment_seconds=4)
    assert [s.relative_major_pc for s in segs] == [0, 7]
    assert segs[0].start == 0
    assert segs[1].relative_major_pc == 7

def test_short_blip_absorbed():
    ws = [W(i, 0) for i in range(10)]
    ws[5] = W(5, 7)   # single spurious G window inside C run
    segs = segment_windows(ws, hop=1.0, min_segment_seconds=4)
    assert len(segs) == 1
    assert segs[0].relative_major_pc == 0

def test_none_windows_ignored_for_boundaries():
    ws = [W(i, 0) for i in range(5)] + [W(5, None, conf=0.1)] + [W(6+i, 0) for i in range(5)]
    segs = segment_windows(ws, hop=1.0, min_segment_seconds=3)
    assert len(segs) == 1
    assert segs[0].relative_major_pc == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_timeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'timeline'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/timeline.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_timeline.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/timeline.py tests/test_timeline.py
git commit -m "feat: pure window->segment timeline logic"
```

---

## Task 3: analyze_timeline (DSP injection) + Timeline.lookup

**Files:**
- Modify: `src/timeline.py`
- Test: `tests/test_timeline.py`

**Interfaces:**
- Consumes: `segment_windows`, `WindowKey`, `Segment`, `key_detection.detect_key`.
- Produces:
  - `analyze_timeline(samples, sr, *, window_seconds, hop_seconds, min_segment_seconds, conf_threshold, detect=detect_key) -> list[Segment]`
  - `class Timeline(segments)` with `.lookup(t) -> Segment|None` and `.segments`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_timeline.py
import numpy as np
from timeline import analyze_timeline, Timeline
from types import SimpleNamespace as NS

def _fake_detect_factory(plan):
    """plan: liste af (pc, conf) i vinduesraekkefoelge."""
    calls = {"i": 0}
    def fake(samples, sr):
        pc, conf = plan[min(calls["i"], len(plan) - 1)]
        calls["i"] += 1
        return NS(relative_major_pc=pc, key="C", mode="major", confidence=conf,
                  pitch_class=pc, margin=0.2)
    return fake

def test_analyze_builds_segments_with_injected_detect():
    sr = 22050
    samples = np.zeros(sr * 16, dtype=np.float32)   # 16s
    plan = [(0, 0.7)] * 8 + [(7, 0.7)] * 8
    segs = analyze_timeline(samples, sr, window_seconds=8, hop_seconds=1.0,
                            min_segment_seconds=4, conf_threshold=0.4,
                            detect=_fake_detect_factory(plan))
    assert [s.relative_major_pc for s in segs] == [0, 7]

def test_low_conf_window_becomes_none_pc():
    sr = 22050
    samples = np.zeros(sr * 10, dtype=np.float32)
    plan = [(0, 0.7)] * 10
    plan[5] = (3, 0.1)   # under threshold -> None
    segs = analyze_timeline(samples, sr, window_seconds=8, hop_seconds=1.0,
                            min_segment_seconds=3, conf_threshold=0.4,
                            detect=_fake_detect_factory(plan))
    assert len(segs) == 1 and segs[0].relative_major_pc == 0

def test_timeline_lookup():
    segs = [Segment(0, 10, 0, "C", "major", 0.7), Segment(10, 20, 7, "G", "major", 0.7)]
    tl = Timeline(segs)
    assert tl.lookup(5).relative_major_pc == 0
    assert tl.lookup(15).relative_major_pc == 7
    assert tl.lookup(25).relative_major_pc == 7   # past end clamps to last
    assert tl.lookup(-1).relative_major_pc == 0   # before start clamps to first

def test_timeline_lookup_empty():
    assert Timeline([]).lookup(5) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_timeline.py -v`
Expected: FAIL with `ImportError: cannot import name 'analyze_timeline'`

- [ ] **Step 3: Write minimal implementation**

Add to top of `src/timeline.py` imports:

```python
import numpy as np
from key_detection import detect_key
```

Append to `src/timeline.py`:

```python
def analyze_timeline(samples, sr, *, window_seconds, hop_seconds,
                     min_segment_seconds, conf_threshold, detect=detect_key):
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_timeline.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/timeline.py tests/test_timeline.py
git commit -m "feat: analyze_timeline (injected detect) + Timeline.lookup"
```

---

## Task 4: TimelineDriver + MidiSink

**Files:**
- Create: `src/timeline_driver.py`
- Test: `tests/test_timeline_driver.py`

**Interfaces:**
- Consumes: `Timeline` (with `.lookup`), `Segment`.
- Produces:
  - `class MidiSink` with `send_key(pc: int)`, `set_retune(on: bool)`, `close()`.
  - `class TimelineDriver(timeline, sink, lookahead_seconds, manual=None)` with `on_position(t: float) -> None`, `set_manual_key(pc)`, `clear_manual()`. Sends key only on change; retune ON when looked-up segment pc is not None, OFF when None.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_timeline_driver.py
from timeline import Timeline, Segment
from timeline_driver import TimelineDriver

class FakeSink:
    def __init__(self): self.keys = []; self.retunes = []
    def send_key(self, pc): self.keys.append(pc)
    def set_retune(self, on): self.retunes.append(on)
    def close(self): pass

def _tl():
    return Timeline([Segment(0, 10, 0, "C", "major", 0.7),
                     Segment(10, 20, 7, "G", "major", 0.7)])

def test_sends_key_once_per_change():
    s = FakeSink(); d = TimelineDriver(_tl(), s, lookahead_seconds=0.0)
    for t in [0, 1, 2, 3]: d.on_position(t)
    assert s.keys == [0]            # only first send

def test_lookahead_switches_early():
    s = FakeSink(); d = TimelineDriver(_tl(), s, lookahead_seconds=1.0)
    d.on_position(8.0)              # 8+1=9 -> still C
    d.on_position(9.5)             # 9.5+1=10.5 -> G, early
    assert s.keys == [0, 7]

def test_retune_off_on_unknown_segment():
    tl = Timeline([Segment(0, 10, None, "C", "major", 0.1)])
    s = FakeSink(); d = TimelineDriver(tl, s, lookahead_seconds=0.0)
    d.on_position(1.0)
    assert s.retunes[-1] is False
    assert s.keys == []            # no key sent for unknown

def test_manual_lock_overrides_timeline():
    s = FakeSink(); d = TimelineDriver(_tl(), s, lookahead_seconds=0.0)
    d.set_manual_key(5)
    d.on_position(1.0); d.on_position(15.0)
    assert s.keys == [5]           # timeline ignored while locked
    d.clear_manual(); d.on_position(15.0)
    assert s.keys == [5, 7]        # resumes from timeline
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_timeline_driver.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'timeline_driver'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/timeline_driver.py
"""Tidslinje -> MIDI med look-ahead. Driver er ren logik (sink injiceres),
MidiSink wrapper midi_output til rigtig hardware."""
import mido
from midi_output import open_port, send_key, load_cc_map


class MidiSink:
    def __init__(self, cfg):
        m = cfg["midi"]
        self.ch = int(m["channel"]); self.cc = int(m["cc_key"]); self.cc_rt = int(m["cc_retune_speed"])
        self.rt_sure = int(m["retune_sure"]); self.rt_unsure = int(m["retune_unsure"])
        self.cc_map, _ = load_cc_map()
        self.out = open_port(m["port_match"], None)
        self._retune = None
        self.set_retune(False)

    def send_key(self, pc):
        send_key(self.out, self.ch, self.cc, self.cc_map, pc)

    def set_retune(self, on):
        if on == self._retune:
            return
        val = self.rt_sure if on else self.rt_unsure
        self.out.send(mido.Message("control_change", channel=self.ch, control=self.cc_rt, value=val))
        self._retune = on

    def close(self):
        self.out.close()


class TimelineDriver:
    def __init__(self, timeline, sink, lookahead_seconds, manual=None):
        self.timeline = timeline
        self.sink = sink
        self.lookahead = float(lookahead_seconds)
        self.last_pc = None
        self.manual_pc = manual

    def set_manual_key(self, pc):
        self.manual_pc = pc
        self.last_pc = pc
        self.sink.send_key(pc)
        self.sink.set_retune(True)

    def clear_manual(self):
        self.manual_pc = None
        self.last_pc = None   # lad tidslinjen laase paa ny

    def on_position(self, t):
        if self.manual_pc is not None:
            return
        seg = self.timeline.lookup(t + self.lookahead)
        if seg is None:
            return
        if seg.relative_major_pc is None:
            self.sink.set_retune(False)
            return
        if seg.relative_major_pc != self.last_pc:
            self.last_pc = seg.relative_major_pc
            self.sink.send_key(seg.relative_major_pc)
        self.sink.set_retune(True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_timeline_driver.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/timeline_driver.py tests/test_timeline_driver.py
git commit -m "feat: TimelineDriver with look-ahead + MidiSink"
```

---

## Task 5: Audio fetch with cache

**Files:**
- Create: `src/audio_fetch.py`
- Test: `tests/test_audio_fetch.py`

**Interfaces:**
- Produces: `fetch_audio(video_id, cache_dir, *, runner=subprocess.run, loader=librosa.load, sr=22050) -> (np.ndarray, int)`. Downloads `bestaudio` to `cache_dir/<video_id>.m4a` via yt-dlp if not cached, then loads mono at `sr`. Re-uses cached file on second call (runner not invoked).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_audio_fetch.py
import os, numpy as np
from audio_fetch import fetch_audio

def test_downloads_then_caches(tmp_path):
    calls = {"n": 0}
    def fake_runner(cmd, **kw):
        calls["n"] += 1
        # simuler yt-dlp output: opret filen den ville lave
        out = [c for c in cmd]
        # find -o target
        target = out[out.index("-o") + 1].replace("%(ext)s", "m4a")
        open(target, "wb").close()
        class R: returncode = 0; stderr = ""
        return R()
    def fake_loader(path, sr=22050, mono=True):
        return np.ones(sr * 2, dtype=np.float32), sr
    y, sr = fetch_audio("ABC123", str(tmp_path), runner=fake_runner, loader=fake_loader)
    assert sr == 22050 and len(y) == 22050 * 2
    assert calls["n"] == 1
    # anden gang: cache hit, ingen download
    y2, _ = fetch_audio("ABC123", str(tmp_path), runner=fake_runner, loader=fake_loader)
    assert calls["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_audio_fetch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'audio_fetch'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/audio_fetch.py
"""Hent YouTube-lyd (yt-dlp) + cache pr. video_id. Loader/runner injicerbar (test)."""
import glob
import os
import subprocess

import librosa


def fetch_audio(video_id, cache_dir, *, runner=subprocess.run, loader=librosa.load, sr=22050):
    os.makedirs(cache_dir, exist_ok=True)
    existing = glob.glob(os.path.join(cache_dir, f"{video_id}.*"))
    if not existing:
        target = os.path.join(cache_dir, f"{video_id}.%(ext)s")
        cmd = ["yt-dlp", "-f", "bestaudio", "--no-playlist",
               "-o", target, f"https://www.youtube.com/watch?v={video_id}"]
        r = runner(cmd, capture_output=True, text=True)
        if getattr(r, "returncode", 1) != 0:
            raise RuntimeError(f"yt-dlp fejl: {getattr(r, 'stderr', '')[:300]}")
        existing = glob.glob(os.path.join(cache_dir, f"{video_id}.*"))
        if not existing:
            raise RuntimeError("yt-dlp: ingen lyd-fil produceret")
    y, out_sr = loader(existing[0], sr=sr, mono=True)
    return y, out_sr
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_audio_fetch.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/audio_fetch.py tests/test_audio_fetch.py
git commit -m "feat: yt-dlp audio fetch with per-video cache"
```

---

## Task 6: YouTube search wrapper

**Files:**
- Create: `src/youtube_search.py`
- Test: (covered in `tests/test_server.py` via mock; add a thin unit test here)
- Test: `tests/test_youtube_search.py`

**Interfaces:**
- Produces: `search(query, api_key, max_results=12, *, fetcher=_http_get_json) -> list[dict]` returning `[{"videoId","title","channel","thumbnail"}]`. Raises `ValueError("no api key")` if `api_key` falsy.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_youtube_search.py
import pytest
from youtube_search import search

def test_requires_api_key():
    with pytest.raises(ValueError):
        search("q", "", 5)

def test_parses_results():
    fake = {"items": [
        {"id": {"videoId": "v1"},
         "snippet": {"title": "Song A", "channelTitle": "Chan",
                     "thumbnails": {"medium": {"url": "http://t/1.jpg"}}}}
    ]}
    out = search("q", "KEY", 5, fetcher=lambda url: fake)
    assert out == [{"videoId": "v1", "title": "Song A", "channel": "Chan",
                    "thumbnail": "http://t/1.jpg"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_youtube_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'youtube_search'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/youtube_search.py
"""YouTube Data API v3 search.list wrapper. API-noegle fra config.local.json."""
import json
import urllib.parse
import urllib.request

_API = "https://www.googleapis.com/youtube/v3/search"


def _http_get_json(url):
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.loads(r.read().decode())


def search(query, api_key, max_results=12, *, fetcher=_http_get_json):
    if not api_key:
        raise ValueError("no api key")
    qs = urllib.parse.urlencode({
        "part": "snippet", "q": query, "type": "video",
        "maxResults": max_results, "key": api_key})
    data = fetcher(f"{_API}?{qs}")
    out = []
    for it in data.get("items", []):
        sn = it.get("snippet", {})
        thumb = sn.get("thumbnails", {}).get("medium", {}).get("url", "")
        out.append({"videoId": it["id"]["videoId"], "title": sn.get("title", ""),
                    "channel": sn.get("channelTitle", ""), "thumbnail": thumb})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_youtube_search.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/youtube_search.py tests/test_youtube_search.py
git commit -m "feat: YouTube Data API search wrapper"
```

---

## Task 7: Backend server (REST + websocket)

**Files:**
- Create: `src/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `appconfig.load_merged_config/get_cache_dir`, `youtube_search.search`, `audio_fetch.fetch_audio`, `timeline.analyze_timeline/Timeline`, `timeline_driver.TimelineDriver/MidiSink`.
- Produces: FastAPI `app`; module-level `STATE` dict holding `{"timeline": Timeline|None, "driver": TimelineDriver|None, "video_id": str|None}`; functions `build_timeline(video_id) -> Timeline` (uses fetch+analyze) so tests can monkeypatch. Endpoints:
  - `GET /api/search?q=` → `{"items":[...]}` or `{"error":...}`.
  - `POST /api/load` body `{"videoId":...}` → builds timeline, stores in STATE → `{"status":"ready","segments":[...]}`.
  - `GET /api/timeline/{video_id}` → `{"segments":[...]}` or 404.
  - `WS /ws` → recv `{"type":"position","t":float}` → drives MIDI; recv `{"type":"manual","pc":int}` / `{"type":"auto"}`.
  - `GET /` and `GET /app.js`,`/style.css` → static from `src/web`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server.py
from fastapi.testclient import TestClient
import server
from timeline import Timeline, Segment

def setup_function(_):
    server.STATE.update({"timeline": None, "driver": None, "video_id": None})

def test_search_no_key(monkeypatch):
    monkeypatch.setattr(server, "CFG", {"youtube": {"search_max_results": 5}})  # no api_key
    c = TestClient(server.app)
    r = c.get("/api/search", params={"q": "abba"})
    assert r.status_code == 200
    assert "error" in r.json()

def test_load_builds_and_stores_timeline(monkeypatch):
    segs = [Segment(0, 10, 0, "C", "major", 0.7), Segment(10, 20, 7, "G", "major", 0.7)]
    monkeypatch.setattr(server, "build_timeline", lambda vid: Timeline(segs))
    monkeypatch.setattr(server, "make_sink", lambda: _FakeSink())
    c = TestClient(server.app)
    r = c.post("/api/load", json={"videoId": "abc"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert [s["relative_major_pc"] for s in body["segments"]] == [0, 7]
    assert server.STATE["video_id"] == "abc"

def test_timeline_404_when_absent():
    c = TestClient(server.app)
    assert c.get("/api/timeline/nope").status_code == 404

class _FakeSink:
    def send_key(self, pc): pass
    def set_retune(self, on): pass
    def close(self): pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/server.py
"""Lokal web-app backend: soeg, load (byg tidslinje), websocket (position -> MIDI)."""
import json
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import FileResponse, JSONResponse

from appconfig import load_merged_config, get_cache_dir
from audio_fetch import fetch_audio
from timeline import analyze_timeline, Timeline
from timeline_driver import TimelineDriver, MidiSink
import youtube_search

CFG = load_merged_config()
WEB = os.path.join(os.path.dirname(__file__), "web")
app = FastAPI()
STATE = {"timeline": None, "driver": None, "video_id": None}


def make_sink():
    return MidiSink(CFG)


def build_timeline(video_id):
    cache = get_cache_dir(CFG)
    y, sr = fetch_audio(video_id, cache, sr=int(CFG["detection"]["analysis_samplerate"]))
    t = CFG["timeline"]
    segs = analyze_timeline(y, sr, window_seconds=t["window_seconds"], hop_seconds=t["hop_seconds"],
                            min_segment_seconds=t["min_segment_seconds"], conf_threshold=t["conf_threshold"])
    return Timeline(segs)


def _segs_json(tl):
    return [{"start": s.start, "end": s.end, "relative_major_pc": s.relative_major_pc,
             "key": s.key, "mode": s.mode, "confidence": s.confidence} for s in tl.segments]


@app.get("/api/search")
def api_search(q: str):
    key = CFG.get("youtube", {}).get("api_key", "")
    mx = CFG.get("youtube", {}).get("search_max_results", 12)
    try:
        return {"items": youtube_search.search(q, key, mx)}
    except ValueError:
        return {"error": "Ingen API-noegle. Tilfoej youtube.api_key i config.local.json."}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/load")
async def api_load(body: dict):
    vid = body.get("videoId")
    if not vid:
        return JSONResponse({"error": "mangler videoId"}, status_code=400)
    tl = build_timeline(vid)
    if STATE["driver"] is None:
        STATE["driver"] = TimelineDriver(tl, make_sink(), CFG["player"]["lookahead_seconds"])
    else:
        STATE["driver"].timeline = tl
        STATE["driver"].last_pc = None
    STATE["timeline"] = tl
    STATE["video_id"] = vid
    return {"status": "ready", "segments": _segs_json(tl)}


@app.get("/api/timeline/{video_id}")
def api_timeline(video_id: str):
    if STATE["video_id"] != video_id or STATE["timeline"] is None:
        return JSONResponse({"error": "ikke fundet"}, status_code=404)
    return {"segments": _segs_json(STATE["timeline"])}


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    try:
        while True:
            msg = json.loads(await sock.receive_text())
            d = STATE["driver"]
            if msg.get("type") == "position" and d:
                d.on_position(float(msg["t"]))
            elif msg.get("type") == "manual" and d:
                d.set_manual_key(int(msg["pc"]))
            elif msg.get("type") == "auto" and d:
                d.clear_manual()
    except WebSocketDisconnect:
        pass


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"))


@app.get("/app.js")
def appjs():
    return FileResponse(os.path.join(WEB, "app.js"))


@app.get("/style.css")
def style():
    return FileResponse(os.path.join(WEB, "style.css"))
```

- [ ] **Step 4: Create placeholder web files so static routes resolve in tests**

```bash
mkdir -p src/web
printf '<!doctype html><title>AL_KEY</title>\n' > src/web/index.html
printf '/* app */\n' > src/web/app.js
printf '/* style */\n' > src/web/style.css
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_server.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/server.py tests/test_server.py src/web/
git commit -m "feat: FastAPI backend (search/load/timeline/ws)"
```

---

## Task 8: Frontend (IFrame player + position stream + status)

**Files:**
- Modify: `src/web/index.html`, `src/web/app.js`, `src/web/style.css`

**Interfaces:**
- Consumes: backend `/api/search`, `/api/load`, `/ws`. YouTube IFrame Player API.
- Produces: working UI (manual/E2E verified). No unit test (browser/DOM); verified by running the app.

- [ ] **Step 1: Write `index.html`**

```html
<!doctype html>
<html lang="da">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>AL_KEY DETECTOR — YouTube</title>
  <link rel="stylesheet" href="/style.css"/>
</head>
<body>
  <header>
    <input id="q" placeholder="Søg YouTube eller indsæt URL…" autocomplete="off"/>
    <button id="go">Søg</button>
  </header>
  <main>
    <section id="results"></section>
    <section id="stage">
      <div id="player"></div>
      <div id="status">
        <div>Toneart: <b id="key">—</b></div>
        <div>Autotune: <b id="rt">FRA</b></div>
        <div>Tidslinje: <b id="tl">—</b></div>
        <div id="manual"></div>
        <button id="auto">Auto</button>
      </div>
    </section>
  </main>
  <script src="https://www.youtube.com/iframe_api"></script>
  <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `app.js`**

```javascript
const NOTES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
let player, ws, lastVid = null;

function connectWS() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onclose = () => setTimeout(connectWS, 1000);
}
connectWS();

function parseVideoId(s) {
  const m = s.match(/(?:v=|youtu\.be\/|\/watch\?.*v=)([\w-]{11})/);
  return m ? m[1] : null;
}

async function search() {
  const q = document.getElementById("q").value.trim();
  const vid = parseVideoId(q);
  if (vid) { load(vid); return; }
  const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
  const d = await r.json();
  const box = document.getElementById("results");
  box.innerHTML = "";
  if (d.error) { box.textContent = d.error; return; }
  for (const it of d.items) {
    const el = document.createElement("div");
    el.className = "result";
    el.innerHTML = `<img src="${it.thumbnail}"/><span>${it.title}</span><small>${it.channel}</small>`;
    el.onclick = () => load(it.videoId);
    box.appendChild(el);
  }
}

async function load(vid) {
  document.getElementById("tl").textContent = "analyserer…";
  document.getElementById("results").innerHTML = "";
  if (player) player.loadVideoById(vid); else createPlayer(vid);
  lastVid = vid;
  const r = await fetch("/api/load", {method:"POST", headers:{"Content-Type":"application/json"},
                                       body: JSON.stringify({videoId: vid})});
  const d = await r.json();
  document.getElementById("tl").textContent = d.status === "ready"
    ? `${d.segments.length} segment(er)` : (d.error || "fejl");
}

function createPlayer(vid) {
  player = new YT.Player("player", {
    height: "390", width: "640", videoId: vid,
    events: { onReady: e => e.target.playVideo() }
  });
}
window.onYouTubeIframeAPIReady = () => {};

// position-stream 4x/sek
setInterval(() => {
  if (player && player.getCurrentTime && ws && ws.readyState === 1) {
    const t = player.getCurrentTime();
    ws.send(JSON.stringify({type:"position", t}));
  }
}, 250);

// manuelle knapper
const man = document.getElementById("manual");
NOTES.forEach((n, pc) => {
  const b = document.createElement("button");
  b.textContent = n;
  b.onclick = () => ws.send(JSON.stringify({type:"manual", pc}));
  man.appendChild(b);
});
document.getElementById("auto").onclick = () => ws.send(JSON.stringify({type:"auto"}));
document.getElementById("go").onclick = search;
document.getElementById("q").addEventListener("keydown", e => { if (e.key === "Enter") search(); });
```

- [ ] **Step 3: Write `style.css`**

```css
body { background:#1e1e1e; color:#e0e0e0; font-family:Helvetica,Arial,sans-serif; margin:0; }
header { display:flex; gap:8px; padding:12px; }
#q { flex:1; padding:8px; background:#141414; color:#e0e0e0; border:1px solid #333; }
button { background:#2d2d2d; color:#e0e0e0; border:1px solid #444; padding:8px 12px; cursor:pointer; }
button:hover { background:#3a7afe; }
main { display:flex; gap:12px; padding:12px; }
#results { width:320px; max-height:80vh; overflow:auto; }
.result { display:grid; grid-template-columns:120px 1fr; gap:6px; padding:6px; cursor:pointer; align-items:center; }
.result:hover { background:#2a2a2a; }
.result img { width:120px; border-radius:4px; }
.result small { grid-column:2; color:#888; }
#stage { flex:1; }
#status { margin-top:10px; font-size:15px; line-height:1.8; }
#status b { color:#3ad07a; }
#manual { display:flex; flex-wrap:wrap; gap:4px; margin:8px 0; }
#manual button { width:44px; }
```

- [ ] **Step 4: Update status from server (broadcast key/retune over ws)**

Modify `src/server.py` `ws` handler to push state back after each position. Replace the `if msg.get("type") == "position" and d:` branch body with:

```python
            if msg.get("type") == "position" and d:
                d.on_position(float(msg["t"]))
                await sock.send_text(json.dumps({
                    "type": "state",
                    "pc": d.last_pc,
                    "retune": d.sink_retune()}))
```

Add to `TimelineDriver` in `src/timeline_driver.py` a helper and track retune state. Add `self._retune_on = False` in `__init__`, set it in `on_position` (True/False where `set_retune` is called), and add:

```python
    def sink_retune(self):
        return self._retune_on
```

Update `on_position` to set `self._retune_on = False` before `self.sink.set_retune(False)` and `self._retune_on = True` before the final `self.sink.set_retune(True)`.

Then in `app.js`, handle incoming state in `connectWS`:

```javascript
  ws.onmessage = (e) => {
    const d = JSON.parse(e.data);
    if (d.type === "state") {
      document.getElementById("key").textContent = d.pc == null ? "—" : NOTES[d.pc];
      document.getElementById("rt").textContent = d.retune ? "PÅ" : "FRA";
    }
  };
```

- [ ] **Step 5: Re-run driver tests (ensure helper didn't break logic)**

Run: `PYTHONPATH=src ./venv/bin/pytest tests/test_timeline_driver.py tests/test_server.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add src/web/ src/server.py src/timeline_driver.py
git commit -m "feat: frontend (IFrame player, search, position stream, status)"
```

---

## Task 9: Run entry point + README

**Files:**
- Create: `src/run_web.py`
- Modify: `README.md`

**Interfaces:**
- Produces: `run_web.py` launching uvicorn on `127.0.0.1:8731` and opening the browser.

- [ ] **Step 1: Write `run_web.py`**

```python
# src/run_web.py
"""Start YouTube karaoke-web-app + aabn browser."""
import threading
import webbrowser

import uvicorn

PORT = 8731

if __name__ == "__main__":
    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}/")).start()
    uvicorn.run("server:app", host="127.0.0.1", port=PORT, log_level="info")
```

- [ ] **Step 2: Manual smoke test**

Run: `PYTHONPATH=src ./venv/bin/python src/run_web.py`
Expected: browser opens; paste a YouTube URL; video plays; within ~10-15s status shows "N segment(er)"; MIDI log in UAD reacts. Ctrl-C stops.

- [ ] **Step 3: Document in `README.md`**

Add a section:

```markdown
## YouTube karaoke-mode (tidslinje + look-ahead)

Søg/indsæt en YouTube-video. App'en henter lyden, analyserer HELE sporet til en
toneart-tidslinje, afspiller videoen, og sender CC#16 med look-ahead — så
modulationer midt i sang følges uden lag.

```bash
PYTHONPATH=src ./venv/bin/python src/run_web.py
```

Kræver `ffmpeg` (yt-dlp lyd) og en YouTube Data API-nøgle i `config.local.json`
(`youtube.api_key`) for søgning. URL-indsæt virker uden nøgle.

Det passive live-system (`src/main.py live`, `src/gui.py`) findes stadig som
fallback til ikke-YouTube-kilder.
```

- [ ] **Step 4: Commit**

```bash
git add src/run_web.py README.md
git commit -m "feat: web run entry point + README"
```

---

## Task 10: Full test sweep

- [ ] **Step 1: Run all tests**

Run: `PYTHONPATH=src ./venv/bin/pytest -v`
Expected: all tests in `tests/test_appconfig.py`, `tests/test_timeline.py`, `tests/test_timeline_driver.py`, `tests/test_audio_fetch.py`, `tests/test_youtube_search.py`, `tests/test_server.py` PASS.

- [ ] **Step 2: Verify no secret committed**

Run: `git ls-files | grep -E 'config.local.json' && echo "LEAK" || echo "clean"`
Expected: `clean`

- [ ] **Step 3: Commit any fixups**

```bash
git add -A && git commit -m "test: full sweep green" || echo "nothing to commit"
```

---

## Self-Review Notes

- **Spec coverage:** search (Task 6), audio fetch+cache (Task 5), offline timeline (Tasks 2-3), look-ahead driver (Task 4), IFrame player + position + status (Task 8), config/secrets (Task 1), server/ws (Task 7), run/docs (Task 9), fallback untouched (Global Constraints). Error handling: search no-key/quota (Task 7 `api_search`), yt-dlp failure (Task 5 raises), unknown segments → retune off (Task 4).
- **Deferred from spec (acceptable, note for follow-up):** "analyse starts at select to pre-warm" optimization and title-prior provisional key during analysis are NOT in this plan — load happens on select and analysis is fast enough; add later if start latency annoys.
- **Type consistency:** `Segment.relative_major_pc` used everywhere (incl. `None` for unknown); `TimelineDriver.last_pc`, `sink_retune()`; `fetch_audio(video_id, cache_dir, ...)`; `search(query, api_key, max_results, ...)`; `build_timeline`/`make_sink` monkeypatch seams match Task 7 tests.
```
