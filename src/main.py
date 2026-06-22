"""Fase 3 — fuld pipeline: audio in -> key detection -> MIDI CC#16 til UAD Auto-Tune.

Kobler realtime.Pipeline's stabile-skifte til MIDI-afsendelse via cc_key_map.
Sender KUN ved nyt stabilt skifte (smoothing i Fase 2), aldrig spam. Minor
konverteres til relativ major (relative_major_pc) — scale (CC#17) sendes ikke.

Modes:
  live            Lyt på config-device, send MIDI live.
  file <sti>      Simulér fra fil. Default --no-midi (tør-kør); brug --midi for
                  faktisk at sende (kræver IAC + UAD åben).

Flag:
  --no-midi       Kør detektion uden at sende (= Fase 2 tør-kør).
  --grace N       Vent N sek efter sang-start/reset før første MIDI sendes (default 0;
                  smoothing giver allerede ~30s naturlig grace).

Eksempler:
  ./venv/bin/python src/main.py live
  ./venv/bin/python src/main.py live --no-midi
  ./venv/bin/python src/main.py file '/Users/.../dirtbag.mp4' --fast --midi
"""
import argparse

import mido

from realtime import load_config, Pipeline, run_live_loop, run_file_loop
from key_detection import NOTE_NAMES
from midi_output import open_port, send_key, load_cc_map
from song_lookup import clean_title, lookup_key


class MidiController:
    def __init__(self, cfg):
        m = cfg["midi"]
        self.ch = int(m["channel"])
        self.cc = int(m["cc_key"])
        self.cc_rt = int(m["cc_retune_speed"])
        # CC-vaerdier: knap helt OP = sikker (autotune paa), knap helt NED = usikker.
        # UAD-mapping er omvendt: 0 = knap op, 127 = knap ned.
        self.rt_sure = int(m["retune_sure"])      # knap op
        self.rt_unsure = int(m["retune_unsure"])  # knap ned
        self.sure_hyst = float(cfg["detection"]["confidence_sure"]) - 0.10  # drop-grænse (hysterese)
        self.cc_map, _ = load_cc_map()
        self.out = open_port(m["port_match"], None)
        self.last_pc = None
        self.is_full = False
        self.retune = self.rt_unsure
        # Manuel override (GUI): naar sat, ignorerer auto-detektion.
        self.manual_lock = False        # True -> auto on_stable rører ikke key
        self.manual_retune = None       # None=auto, True=tving op, False=tving ned
        self.on_event = None            # callback(kind, payload) -> GUI-log/status
        self._set_retune(self.rt_unsure)  # start: knap ned, ingen korrektion

    def _emit(self, kind, **payload):
        if self.on_event:
            self.on_event(kind, payload)

    # --- key (CC#16) ---
    def on_stable(self, stable):
        if self.manual_lock:
            return  # bruger styrer key manuelt
        pc = stable.relative_major_pc
        if pc == self.last_pc:
            return  # send kun ændringer
        self.last_pc = pc
        send_key(self.out, self.ch, self.cc, self.cc_map, pc)
        print(f"         >>> MIDI key: {NOTE_NAMES[pc]} "
              f"(CC#{self.cc}={self.cc_map[pc]}) [{stable.key} {stable.mode}]")
        self._emit("key", pc=pc, src="lyd", detail=f"{stable.key} {stable.mode}")

    # --- manuel toneart (GUI-knap) ---
    def set_manual_key(self, pc):
        self.manual_lock = True
        self.last_pc = pc
        send_key(self.out, self.ch, self.cc, self.cc_map, pc)
        print(f"         >>> MANUEL key: {NOTE_NAMES[pc]} (CC#{self.cc}={self.cc_map[pc]})")
        self._emit("key", pc=pc, src="manuel", detail="laast")

    def clear_manual(self):
        self.manual_lock = False
        self.manual_retune = None
        self.last_pc = None  # lad lyd laase paa ny
        self._emit("auto", detail="auto genoptaget")

    def set_manual_retune(self, on):
        """on=True tving autotune paa, False tving fra, None retur til auto."""
        self.manual_retune = on
        if on is None:
            return
        self._set_retune(self.rt_sure if on else self.rt_unsure)

    # --- retune speed (CC#18) drevet af confidence, med hysterese ---
    def on_analysis(self, res, sure, locked_pc):
        if self.manual_retune is not None:
            return  # bruger tvinger retune
        if locked_pc is None:
            want_full = False
        elif self.is_full:
            want_full = res.confidence >= self.sure_hyst  # bliv oppe til conf falder under hysterese
        else:
            want_full = sure
        target = self.rt_sure if want_full else self.rt_unsure
        if target != self.retune:
            self.is_full = want_full
            self._set_retune(target)
            self._emit("retune", on=want_full, src="lyd")

    # --- titel-prior (hybrid): ny YouTube-sang -> laas CC#16 straks ---
    def on_new_title(self, raw):
        artist, title = clean_title(raw)
        if not title:
            return
        print(f"         >>> NY TITEL: {artist or '?'} - {title}")
        self._emit("title", title=title, artist=artist)
        hint = lookup_key(artist, title)
        if not hint:
            print("             (intet bibliotek-fund — venter paa lyd)")
            self._emit("lookup", found=False)
            return
        pc = hint.relative_major_pc
        print(f"             bibliotek: {hint.key_str} -> send-tone {NOTE_NAMES[pc]} "
              f"(prior, lyd bekraefter)")
        self._emit("lookup", found=True, key_str=hint.key_str, pc=pc, strength=hint.strength)
        if self.manual_lock:
            return  # bruger styrer key manuelt — prior springes over
        if pc != self.last_pc:
            self.last_pc = pc
            send_key(self.out, self.ch, self.cc, self.cc_map, pc)
            print(f"         >>> MIDI key (prior): {NOTE_NAMES[pc]} (CC#{self.cc}={self.cc_map[pc]})")
        # Retune forbliver NED — autotune taendes foerst naar LYD bekraefter (transpon.-sikkert).

    def on_reset(self):
        self.last_pc = None
        self.is_full = False
        if self.manual_retune is None:
            self._set_retune(self.rt_unsure)
        self._emit("reset")

    def _set_retune(self, target):
        # Altid ENTEN helt op (sikker) ELLER helt ned (usikker) — aldrig mellemtrin.
        self.out.send(mido.Message("control_change", channel=self.ch, control=self.cc_rt, value=target))
        self.retune = target
        pos = "OP (autotune paa)" if target == self.rt_sure else "NED (autotune fra)"
        print(f"         >>> MIDI retune speed -> {target} = knap {pos} (CC#{self.cc_rt})")

    def close(self):
        self.out.close()


if __name__ == "__main__":
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-midi", action="store_true", help="kør uden at sende MIDI (tør-kør)")
    common.add_argument("--midi", action="store_true", help="(file-mode) send rigtigt MIDI")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("live", parents=[common])
    f = sub.add_parser("file", parents=[common]); f.add_argument("path"); f.add_argument("--fast", action="store_true")
    a = p.parse_args()

    cfg = load_config()
    pipe = Pipeline(cfg)

    want_midi = (a.cmd == "live" and not a.no_midi) or (a.cmd == "file" and a.midi)
    ctrl = None
    if want_midi:
        ctrl = MidiController(cfg)
        pipe.on_stable = ctrl.on_stable
        pipe.on_analysis = ctrl.on_analysis
        pipe.on_reset = ctrl.on_reset
        pipe.on_new_title = ctrl.on_new_title
        print("MIDI: aktiv — CC#16 key + CC#18 retune speed + titel-prior.\n")
    else:
        print("MIDI: FRA (tør-kør) — kun log.\n")

    try:
        if a.cmd == "live":
            run_live_loop(cfg, pipe)
        else:
            run_file_loop(cfg, pipe, a.path, a.fast)
    finally:
        if ctrl:
            ctrl.close()
