# Karaoke Auto-Tune — automatic key control

Listens to Pro Tools audio (karaoke instrumental), detects the musical key in real
time, and sends MIDI CC#16 (Key) to UAD Auto-Tune via the IAC Driver. Scale is
handled with a relative-major trick (minor → relative major), so only CC#16 is used.

## Setup (once)

1. **IAC Driver:** Audio MIDI Setup → MIDI Studio → IAC Driver → "Device is online".
   Confirm the port name contains "IAC".
2. **UAD Console:** MIDI-learn CC#16 to Auto-Tune's Key parameter, channel 1.
3. **Pro Tools:** route the karaoke audio to "Pro Tools Audio Bridge 2-A".
4. Python environment:
   ```
   python3.11 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```

All settings (device, port, CC, thresholds, key mapping) live in `config.json`.

## Run

```bash
# Full operation: listen live + send MIDI
PYTHONPATH=src ./venv/bin/python src/main.py live

# Dry run (detect, NO MIDI)
PYTHONPATH=src ./venv/bin/python src/main.py live --no-midi

# Test against an audio file
PYTHONPATH=src ./venv/bin/python src/main.py file '/path/song.mp4' --fast --midi
```

The program typically locks the correct key ~25-40 sec into a song (it accumulates
from the start of the song). Silence between songs (≥~8s) automatically resets for
a new song.

## Tools (Phase 0 / troubleshooting)

```bash
# Audio devices + MIDI ports
./venv/bin/python src/list_devices.py

# Find which device has signal (play audio while running)
./venv/bin/python src/audio_capture.py probe

# Send a single note manually to Auto-Tune
./venv/bin/python src/midi_output.py key A

# Detect the key of a file
PYTHONPATH=src ./venv/bin/python src/key_detection.py song.wav
```

## Title prior (hybrid)

Grabs the active YouTube tab title from Chrome, looks up the key via MusicBrainz +
AcousticBrainz, and locks CC#16 **immediately** (provisionally) while the audio
buffer fills. Audio detection is ground truth and overrides it (karaoke is often
transposed). Retune (CC#18) is NEVER turned on by the prior alone — only when the
audio confirms.

Source: free, no API key. MusicBrainz only requires a contact email in the
User-Agent (`config.json` → `song_lookup.contact_email`). AcousticBrainz only has
keys for songs others have analyzed — good coverage on hits, gaps on new/obscure
tracks. (GetSongBPM was dropped: their API sits behind a Cloudflare bot challenge,
unusable from a script.) Test:
```bash
./venv/bin/python src/song_lookup.py title     # show cleaned Chrome title
./venv/bin/python src/song_lookup.py lookup     # title -> key
```

## GUI (Phase 4)

```bash
PYTHONPATH=src ./venv/bin/python src/gui.py
```
Shows the YouTube title, the current send-key, autotune status, and a log that
updates on every new event. 12 buttons set the key manually (locks auto until
"Auto" is pressed); each button shows its relative minor below it. Buttons: Auto
(release manual), Autotune ON/OFF (force retune), Reset song.

Requires Tk: `brew install python-tk@3.11` (once). Run the GUI **or** `main.py live`
— not both (they share the audio device).

## Status
- Phase 0 (audio + MIDI plumbing) ✅
- Phase 1 (key detection, 4/4 on test) ✅
- Phase 2 (realtime pipeline + smoothing) ✅
- Phase 3 (MIDI output) ✅ code — pending live UAD confirmation
- Phase 4 (GUI status + log + manual override) ✅
- Phase 5 (robustness, config) — partial (config.json exists)
