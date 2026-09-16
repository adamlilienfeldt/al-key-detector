"""Isolations-test: aabner KUN en InputStream paa Bridge 2-A, callback goer INTET.
Ingen resample, ingen librosa, ingen MIDI. Hvis afspilning hakker mens denne
koerer -> det er selve det at capture fra device'et (routing/klokke), IKKE vores kode.

Kør (afspil musik imens):
  ./venv/bin/python tests/cap_test.py            # default: blocksize 0
  ./venv/bin/python tests/cap_test.py 24000      # stor blocksize (soendags-stil)
"""
import sys
import time
import sounddevice as sd

NAME = "Pro Tools Audio Bridge 2-A"
blocksize = int(sys.argv[1]) if len(sys.argv) > 1 else 0

dev = next((i for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0 and NAME.lower() in d["name"].lower()), None)
if dev is None:
    print(f"FEJL: '{NAME}' ikke fundet"); raise SystemExit(1)

info = sd.query_devices(dev)
sr = int(info["default_samplerate"])
print(f"Aabner [{dev}] {info['name']} @ {sr}Hz, blocksize={blocksize}, channels={min(2,info['max_input_channels'])}")
print("Callback goer INTET. Afspil musik. Ctrl-C for stop.\n")

calls = 0
def cb(indata, frames, t, status):
    global calls
    calls += 1
    if status:
        print("STATUS:", status)  # over/underflow vises her

with sd.InputStream(device=dev, samplerate=sr,
                    channels=min(2, info["max_input_channels"]),
                    dtype="float32", callback=cb, blocksize=blocksize, latency="high"):
    try:
        t0 = time.time()
        while True:
            time.sleep(2)
            print(f"{time.time()-t0:.0f}s | callbacks={calls}")
    except KeyboardInterrupt:
        print("\nStop.")
