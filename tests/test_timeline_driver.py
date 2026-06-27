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
