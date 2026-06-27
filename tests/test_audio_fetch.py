import os, numpy as np
from audio_fetch import fetch_audio, fetch_media_file

def _fake_runner_factory(calls):
    def fake_runner(cmd, **kw):
        calls["n"] += 1
        target = cmd[cmd.index("-o") + 1].replace("%(ext)s", "mp4")
        open(target, "wb").close()
        class R: returncode = 0; stderr = ""
        return R()
    return fake_runner

def test_media_file_downloads_then_caches(tmp_path):
    calls = {"n": 0}
    runner = _fake_runner_factory(calls)
    p1 = fetch_media_file("ABC123", str(tmp_path), runner=runner)
    assert os.path.exists(p1) and calls["n"] == 1
    p2 = fetch_media_file("ABC123", str(tmp_path), runner=runner)   # cache hit
    assert p2 == p1 and calls["n"] == 1

def test_fetch_audio_loads_from_media_file(tmp_path):
    calls = {"n": 0}
    runner = _fake_runner_factory(calls)
    def fake_loader(path, sr=22050, mono=True):
        return np.ones(sr * 2, dtype=np.float32), sr
    y, sr = fetch_audio("ABC123", str(tmp_path), runner=runner, loader=fake_loader)
    assert sr == 22050 and len(y) == 22050 * 2
    assert calls["n"] == 1
    fetch_audio("ABC123", str(tmp_path), runner=runner, loader=fake_loader)   # cache hit
    assert calls["n"] == 1
