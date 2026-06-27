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
