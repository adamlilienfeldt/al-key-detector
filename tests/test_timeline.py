import numpy as np
from types import SimpleNamespace as NS
from timeline import WindowKey, Segment, segment_windows, analyze_timeline, Timeline

def W(t, pc, conf=0.7): return WindowKey(t=t, relative_major_pc=pc, key="X", mode="major", confidence=conf)

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
    samples = np.zeros(sr * 30, dtype=np.float32)   # 30s -> 23 vinduer (win 8s, hop 1s)
    plan = [(0, 0.7)] * 12 + [(7, 0.7)] * 11        # C-run + G-run, begge laenge nok
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
