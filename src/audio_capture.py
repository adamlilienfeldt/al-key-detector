"""Fase 0 — audio capture + level probe.

Subkommandoer:
  probe                Mål signal-niveau (RMS/peak) på ALLE input-devices i ~2 sek hver.
                       Afspil YouTube-karaoke imens -> device med signal = den rigtige.
  meter  --device N    Live level-meter på ét device (Ctrl-C for stop).
  record --device N    Optag 5 sek fra device N -> gem som .wav til afspilning.

Eksempler:
  ./venv/bin/python src/audio_capture.py probe
  ./venv/bin/python src/audio_capture.py meter  --device 3
  ./venv/bin/python src/audio_capture.py record --device 3 --seconds 5 --out test.wav
"""
import argparse
import sys
import numpy as np
import sounddevice as sd
from scipy.io import wavfile


def _rms_peak(block):
    rms = float(np.sqrt(np.mean(block ** 2)))
    peak = float(np.max(np.abs(block))) if block.size else 0.0
    return rms, peak


def _dbfs(x):
    return -120.0 if x <= 1e-6 else 20.0 * np.log10(x)


def probe(seconds=2.0):
    devices = sd.query_devices()
    print(f"Probe {seconds:.0f}s pr. input-device. Afspil karaoke-lyd NU...\n")
    results = []
    for i, d in enumerate(devices):
        if d["max_input_channels"] < 1:
            continue
        sr = int(d["default_samplerate"])
        ch = min(2, d["max_input_channels"])
        try:
            rec = sd.rec(int(seconds * sr), samplerate=sr, channels=ch,
                         device=i, dtype="float32")
            sd.wait()
            rms, peak = _rms_peak(rec)
            results.append((i, d["name"], rms, peak))
            flag = "  <-- SIGNAL" if _dbfs(peak) > -50 else ""
            print(f"[{i:2d}] {d['name'][:34]:34s} "
                  f"peak {_dbfs(peak):6.1f} dBFS  rms {_dbfs(rms):6.1f} dBFS{flag}")
        except Exception as e:
            print(f"[{i:2d}] {d['name'][:34]:34s} FEJL: {e}")
    if results:
        best = max(results, key=lambda r: r[3])
        print(f"\nStærkest signal: [{best[0]}] {best[1]} "
              f"(peak {_dbfs(best[3]):.1f} dBFS)")


def meter(device):
    d = sd.query_devices(device)
    sr = int(d["default_samplerate"])
    ch = min(2, d["max_input_channels"])
    print(f"Live meter device [{device}] {d['name']} ({sr} Hz, {ch} ch). Ctrl-C stop.")

    def cb(indata, frames, t, status):
        rms, peak = _rms_peak(indata)
        bar = "#" * int(max(0, (_dbfs(peak) + 60) / 60 * 40))
        sys.stdout.write(f"\rpeak {_dbfs(peak):6.1f} dBFS |{bar:<40}|")
        sys.stdout.flush()

    try:
        with sd.InputStream(device=device, samplerate=sr, channels=ch,
                            dtype="float32", callback=cb):
            while True:
                sd.sleep(200)
    except KeyboardInterrupt:
        print("\nStop.")


def record(device, seconds, out):
    d = sd.query_devices(device)
    sr = int(d["default_samplerate"])
    ch = min(2, d["max_input_channels"])
    print(f"Optager {seconds}s fra [{device}] {d['name']} ({sr} Hz, {ch} ch)...")
    rec = sd.rec(int(seconds * sr), samplerate=sr, channels=ch,
                 device=device, dtype="float32")
    sd.wait()
    rms, peak = _rms_peak(rec)
    pcm = np.int16(np.clip(rec, -1, 1) * 32767)
    wavfile.write(out, sr, pcm)
    print(f"Gemt: {out}  (peak {_dbfs(peak):.1f} dBFS, rms {_dbfs(rms):.1f} dBFS)")
    if _dbfs(peak) < -50:
        print("ADVARSEL: meget lavt niveau — forkert device, eller ingen lyd afspillet?")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("probe"); sp.add_argument("--seconds", type=float, default=2.0)
    sm = sub.add_parser("meter"); sm.add_argument("--device", type=int, required=True)
    sr_ = sub.add_parser("record")
    sr_.add_argument("--device", type=int, required=True)
    sr_.add_argument("--seconds", type=float, default=5.0)
    sr_.add_argument("--out", default="fase0_test.wav")
    a = p.parse_args()
    if a.cmd == "probe":
        probe(a.seconds)
    elif a.cmd == "meter":
        meter(a.device)
    elif a.cmd == "record":
        record(a.device, a.seconds, a.out)
