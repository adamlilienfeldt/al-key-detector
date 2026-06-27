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
        self._retune_on = False

    def sink_retune(self):
        return self._retune_on

    def set_manual_key(self, pc):
        self.manual_pc = pc
        self.last_pc = pc
        self.sink.send_key(pc)
        self._retune_on = True
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
            self._retune_on = False
            self.sink.set_retune(False)
            return
        if seg.relative_major_pc != self.last_pc:
            self.last_pc = seg.relative_major_pc
            self.sink.send_key(seg.relative_major_pc)
        self._retune_on = True
        self.sink.set_retune(True)
