import os, numpy as np
from audio_fetch import fetch_audio

def test_downloads_then_caches(tmp_path):
    calls = {"n": 0}
    def fake_runner(cmd, **kw):
        calls["n"] += 1
        out = [c for c in cmd]
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
