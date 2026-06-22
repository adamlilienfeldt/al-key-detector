"""Fase 2 — realtids key-detection pipeline (INGEN MIDI endnu).

Rullende ring-buffer fyldes fra audio-input. Hvert N sekund køres key-detection
på de seneste `buffer_seconds` af bufferen. Smoothing afgør stabile skift.
Min-niveau-gate springer stilhed over.

Modes:
  live            Lyt på config'ens audio-device (default).
  file <sti>      Simulér realtid ved at streame en lyd-/video-fil gennem samme
                  pipeline (til test uden live-lyd). Hastighed ~realtid, eller
                  --fast for hurtig gennemkørsel.

Eksempler:
  ./venv/bin/python src/realtime.py live
  ./venv/bin/python src/realtime.py file '/Users/.../dirtbag.mp4' --fast
"""
import argparse
import json
import os
import sys
import time
from collections import deque

import numpy as np

from key_detection import detect_key, NOTE_NAMES
from smoothing import Smoother

CONFIG = os.path.join(os.path.dirname(__file__), "..", "config.json")


def load_config():
    with open(CONFIG) as f:
        return json.load(f)


def _dbfs(x):
    return -120.0 if x <= 1e-6 else 20.0 * np.log10(x)


class Pipeline:
    def __init__(self, cfg):
        d = cfg["detection"]
        self.sr = int(d["analysis_samplerate"])
        # accumulate-fra-start: voksende buffer cappet ved max_buffer_seconds.
        self.max_len = int(d["max_buffer_seconds"] * self.sr)
        self.min_len = int(d["min_buffer_seconds"] * self.sr)
        self.interval = float(d["analysis_interval_seconds"])
        self.min_dbfs = float(d["min_level_dbfs"])
        self.confidence_sure = float(d["confidence_sure"])
        self.silence_reset = int(d["silence_reset_windows"])
        self.buffer = deque(maxlen=self.max_len)
        self.smoother = Smoother(d["stable_windows_required"], d["confidence_threshold"])
        self.last_analysis = 0.0
        self.silence_count = 0
        self.on_stable = None    # callback(StableKey) — nyt stabilt key-skifte -> CC#16
        self.on_analysis = None  # callback(res, sure: bool, locked_pc) — hver analyse -> CC#18
        self.on_reset = None     # callback() — ny sang -> retune ned
        self.on_new_title = None # callback(raw_title) — ny YouTube-sang -> prior-opslag

    def feed(self, mono_samples):
        self.buffer.extend(mono_samples)

    def reset_song(self, ts):
        self.buffer.clear()
        self.smoother.reset()
        print(f"[{ts}] --- stilhed: nulstiller (ny sang), retune NED ---")
        if self.on_reset:
            self.on_reset()

    def maybe_analyze(self, now):
        if now - self.last_analysis < self.interval:
            return
        self.last_analysis = now
        if len(self.buffer) < self.min_len:
            return
        seg = np.fromiter(self.buffer, dtype=np.float32)
        peak = float(np.max(np.abs(seg[-self.sr * 3:]))) if seg.size else 0.0  # niveau på seneste 3s
        ts = time.strftime("%H:%M:%S")
        if _dbfs(peak) < self.min_dbfs:
            self.silence_count += 1
            print(f"[{ts}] stilhed ({_dbfs(peak):.0f} dBFS) [{self.silence_count}/{self.silence_reset}]")
            if self.silence_count >= self.silence_reset:
                self.reset_song(ts)
            return
        self.silence_count = 0
        res = detect_key(seg, self.sr)
        stable = self.smoother.update(res)
        locked_pc = self.smoother.current_stable
        # "sikker" = vi har laast et key OG seneste confidence er hoej nok.
        sure = locked_pc is not None and res.confidence >= self.confidence_sure
        tag = "STABIL ->" if stable else "         "
        relmaj = NOTE_NAMES[res.relative_major_pc]
        rt = "FULD" if sure else "ned "
        print(f"[{ts}] {tag} {res.key} {res.mode:5s} | relmaj {relmaj:2s} "
              f"| conf {res.confidence:.2f} margin {res.margin:.2f} "
              f"| retune {rt} | buf {len(self.buffer)/self.sr:.0f}s")
        if stable:
            print(f"         >>> KEY-SKIFTE: send-tone = {NOTE_NAMES[stable.relative_major_pc]} "
                  f"(CC#16) [{stable.key} {stable.mode}]")
            if self.on_stable:
                self.on_stable(stable)
        if self.on_analysis:
            self.on_analysis(res, sure, locked_pc)


def resolve_device(cfg, sd):
    """Find audio-input device. Match paa navn hvis muligt (robust mod index-skift),
    ellers brug device_index."""
    a = cfg["audio"]
    if a.get("match_by_name") and a.get("device_name"):
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and a["device_name"].lower() in d["name"].lower():
                if i != a.get("device_index"):
                    print(f"(device '{a['device_name']}' fundet paa index {i}, "
                          f"config sagde {a.get('device_index')})")
                return i
        print(f"ADVARSEL: device '{a['device_name']}' ikke fundet — bruger index {a['device_index']}")
    return a["device_index"]


def run_live_loop(cfg, pipe, stop=None):
    import sounddevice as sd
    import scipy.signal as sps
    a = cfg["audio"]
    dev = resolve_device(cfg, sd)
    in_sr = int(sd.query_devices(dev)["default_samplerate"])
    ratio = pipe.sr / in_sr
    print(f"Live: device [{dev}] {a['device_name']} {in_sr}Hz -> analyse {pipe.sr}Hz. Ctrl-C stop.\n")

    # Titel-watch (hybrid prior): poll Chrome-tab, fyr on_new_title ved skift.
    sl = cfg.get("song_lookup", {})
    title_on = bool(sl.get("enabled")) and pipe.on_new_title is not None
    title_poll = float(sl.get("poll_seconds", 2.0))
    last_title = None
    last_title_check = 0.0
    if title_on:
        from song_lookup import chrome_title

    def cb(indata, frames, t, status):
        mono = indata.mean(axis=1) if indata.ndim > 1 else indata
        n = max(1, int(len(mono) * ratio))
        pipe.feed(sps.resample(mono, n).astype(np.float32))

    start = time.time()
    with sd.InputStream(device=dev, samplerate=in_sr, channels=min(2, sd.query_devices(dev)["max_input_channels"]),
                        dtype="float32", callback=cb, blocksize=int(in_sr * 0.5)):
        try:
            while stop is None or not stop.is_set():
                now = time.time() - start
                pipe.maybe_analyze(now)
                if title_on and now - last_title_check >= title_poll:
                    last_title_check = now
                    cur = chrome_title()
                    if cur and cur != last_title:
                        last_title = cur
                        pipe.on_new_title(cur)
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\nStop.")


def run_file_loop(cfg, pipe, path, fast):
    import librosa
    print(f"Fil-sim: {path} {'(fast)' if fast else '(realtid)'}\n")
    y, _ = librosa.load(path, sr=pipe.sr, mono=True)
    chunk = int(pipe.sr * 0.5)  # 0.5s blokke
    t = 0.0
    for i in range(0, len(y), chunk):
        pipe.feed(y[i:i + chunk])
        t += 0.5
        pipe.maybe_analyze(t)
        if not fast:
            time.sleep(0.5)
    print("\nFil slut.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("live")
    f = sub.add_parser("file"); f.add_argument("path"); f.add_argument("--fast", action="store_true")
    a = p.parse_args()
    cfg = load_config()
    pipe = Pipeline(cfg)
    if a.cmd == "live":
        run_live_loop(cfg, pipe)
    else:
        run_file_loop(cfg, pipe, a.path, a.fast)
