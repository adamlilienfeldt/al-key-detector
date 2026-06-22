"""Fase 0 / Fase 3 — MIDI CC sender til UAD Auto-Tune via IAC.

CC#16 -> Key, CC#17 -> Scale (mapping skal verificeres i UAD Console).

Subkommandoer:
  ports                          List MIDI output-porte.
  send  --cc N --val V           Send én CC-besked (Fase 0 test).
  sweep --cc N [--vals 0,1,..]   Send en række CC-værdier med pause imellem,
                                  prompt for hvad UAD Console viser ved hver
                                  -> kortlæg værdi->toneart. Logger til map_cc<N>.txt
  scan-key                       Sweep CC#16 over 0..11 (key-mapping).
  scan-scale                     Sweep CC#17 over 0,1 (major/minor).

Default port-match: "IAC". Override med --port "<navn>". Kanal --ch (0-indekseret).

Eksempler:
  ./venv/bin/python src/midi_output.py ports
  ./venv/bin/python src/midi_output.py send --cc 16 --val 0
  ./venv/bin/python src/midi_output.py scan-key
"""
import argparse
import json
import os
import time
import mido

DEFAULT_MATCH = "IAC"
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_ALIASES = {"DB": 1, "EB": 3, "GB": 6, "AB": 8, "BB": 10}
_CONFIG = os.path.join(os.path.dirname(__file__), "..", "config.json")


def load_cc_map():
    with open(_CONFIG) as f:
        cfg = json.load(f)
    raw = cfg["cc_key_map"]
    return {int(k): v for k, v in raw.items() if k.isdigit()}, cfg


def note_to_pc(name):
    n = name.strip().upper().replace("♯", "#").replace("♭", "B")
    if n in _ALIASES:
        return _ALIASES[n]
    if n in NOTE_NAMES:
        return NOTE_NAMES.index(n)
    raise SystemExit(f"Ukendt tone '{name}'. Brug C, C#, Db, D, ... B")


def send_key(out, ch, cc, cc_map, pc):
    val = cc_map[pc]
    out.send(mido.Message("control_change", channel=ch, control=cc, value=val))
    print(f"Key {NOTE_NAMES[pc]} -> ch{ch} CC#{cc} = {val}")


def find_port(match):
    for n in mido.get_output_names():
        if match.lower() in n.lower():
            return n
    raise SystemExit(f"Ingen MIDI-port matcher '{match}'. Porte: {mido.get_output_names()}")


def open_port(match, port):
    name = port if port else find_port(match)
    print(f"MIDI port: {name}")
    return mido.open_output(name)


def cmd_ports():
    for n in mido.get_output_names():
        print(f"  - {n}")


def cmd_send(out, ch, cc, val):
    out.send(mido.Message("control_change", channel=ch, control=cc, value=val))
    print(f"Sendt: ch{ch} CC#{cc} = {val}")


def cmd_sweep(out, ch, cc, vals, label):
    log = []
    print(f"Sweep CC#{cc} på kanal {ch}. Hold UAD Console MIDI-learn/param synlig.\n")
    for v in vals:
        out.send(mido.Message("control_change", channel=ch, control=cc, value=v))
        ans = input(f"  CC#{cc}={v:3d} sendt -> hvad viser UAD Console? (Enter=skip) > ").strip()
        log.append((v, ans))
    fname = f"map_cc{cc}.txt"
    with open(fname, "w") as f:
        f.write(f"# {label} — CC#{cc}, kanal {ch}\n")
        f.write("value\tuad_viser\n")
        for v, a in log:
            f.write(f"{v}\t{a}\n")
    print(f"\nMapping gemt: {fname}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", default=None, help="eksakt portnavn (ellers match IAC)")
    p.add_argument("--match", default=DEFAULT_MATCH)
    p.add_argument("--ch", type=int, default=0, help="MIDI-kanal 0-indekseret")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports")
    s = sub.add_parser("send"); s.add_argument("--cc", type=int, required=True); s.add_argument("--val", type=int, required=True)
    sw = sub.add_parser("sweep"); sw.add_argument("--cc", type=int, required=True); sw.add_argument("--vals", default=None)
    sub.add_parser("scan-key")
    sub.add_parser("scan-scale")
    k = sub.add_parser("key"); k.add_argument("note", help="tonenavn, fx A eller Db")
    sub.add_parser("verify-keys")
    a = p.parse_args()

    if a.cmd == "ports":
        cmd_ports()
        raise SystemExit

    out = open_port(a.match, a.port)
    with out:
        if a.cmd == "send":
            cmd_send(out, a.ch, a.cc, a.val)
        elif a.cmd == "key":
            cc_map, _ = load_cc_map()
            send_key(out, a.ch, 16, cc_map, note_to_pc(a.note))
        elif a.cmd == "verify-keys":
            cc_map, _ = load_cc_map()
            print("Sender alle 12 toner fra config. Bekraeft hver i UAD Console.\n")
            for pc in range(12):
                send_key(out, a.ch, 16, cc_map, pc)
                input("  Enter = naeste > ")
        elif a.cmd == "sweep":
            vals = [int(x) for x in a.vals.split(",")] if a.vals else list(range(0, 12))
            cmd_sweep(out, a.ch, a.cc, vals, "manuel sweep")
        elif a.cmd == "scan-key":
            cmd_sweep(out, a.ch, 16, list(range(0, 12)), "Key-mapping")
        elif a.cmd == "scan-scale":
            cmd_sweep(out, a.ch, 17, [0, 1], "Scale-mapping (major/minor)")
