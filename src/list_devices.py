"""Fase 0 — list alle audio devices + MIDI porte synlige for Python.

Kør: ./venv/bin/python src/list_devices.py
"""
import sounddevice as sd
import mido


def list_audio():
    print("=" * 60)
    print("AUDIO DEVICES (sounddevice / PortAudio)")
    print("=" * 60)
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        io = []
        if d["max_input_channels"] > 0:
            io.append(f"in:{d['max_input_channels']}")
        if d["max_output_channels"] > 0:
            io.append(f"out:{d['max_output_channels']}")
        print(f"[{i:2d}] {d['name']}")
        print(f"      {', '.join(io)} | {d['default_samplerate']:.0f} Hz "
              f"| host: {sd.query_hostapis(d['hostapi'])['name']}")
    print()
    print(f"Default input : {sd.default.device[0]}")
    print(f"Default output: {sd.default.device[1]}")


def list_midi():
    print()
    print("=" * 60)
    print("MIDI OUTPUT PORTS (mido / rtmidi)")
    print("=" * 60)
    names = mido.get_output_names()
    if not names:
        print("  (ingen MIDI output-porte fundet — er IAC Driver aktiveret?)")
    for n in names:
        print(f"  - {n}")


if __name__ == "__main__":
    list_audio()
    list_midi()
