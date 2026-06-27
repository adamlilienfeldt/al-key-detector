# Karaoke Auto-Tune — automatic key control

Listens to Pro Tools audio (karaoke instrumental), detects the musical key in real
time, and sends MIDI CC#16 (Key) to UAD Auto-Tune via the IAC Driver. Scale is
handled with a relative-major trick (minor → relative major), so only CC#16 is used.

## Setup (once)

1. **IAC Driver:** Audio MIDI Setup → MIDI Studio → IAC Driver → "Device is online".
   Confirm the port name contains "IAC".
2. **UAD Console:** MIDI-learn CC#16 to Auto-Tune's Key parameter, channel 1.
3. **Audio routing:** set the system output to a Multi-Output device (e.g. speakers +
   BlackHole) so playback is captured from the BlackHole loopback. Capturing from the
   Pro Tools Bridge pulled playback speed down (clock race); BlackHole does not.
   The capture device is set in `config.json` → `audio` (currently BlackHole).
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

The audio path locks the key in ~4s from the start of a song (`min_buffer 3s` +
2 stable windows at `interval 1.0s`); it accumulates from the start. When a library
hit exists, the prior locks the key and turns autotune on **immediately** (see below).

**Reset / breaks / song switch:** autotune stays **on** through breaks and pauses —
silence alone never turns it off or resets the key. A full reset (clear buffer + key,
retune down) happens when the **browser tab title changes** (= new song). A long
silence (~20s, `silence_reset_windows`) is a safety fallback for "song ended, no
title". Pausing and resuming the same video does not change the title, so it keeps
the key and the displayed title.

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
AcousticBrainz, locks CC#16 **immediately**, and turns autotune (CC#18) **on right
away** on the library key. Audio detection then confirms or corrects it: if the song
is transposed, the audio locks a different key within ~4s and overrides both the key
and (via confidence) the retune state. Songs with no library hit fall back to the
audio path alone (~4s lock).

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

## YouTube karaoke-mode (tidslinje + look-ahead)

Søg/indsæt en YouTube-video. App'en henter lyden, analyserer HELE sporet til en
toneart-tidslinje, afspiller videoen, og sender CC#16 med look-ahead — så
modulationer midt i sang følges uden lag.

```bash
PYTHONPATH=src ./venv/bin/python src/run_web.py
```

Kræver `ffmpeg` (yt-dlp lyd) og en YouTube Data API-nøgle i `config.local.json`
(`youtube.api_key`) for søgning. URL-indsæt virker uden nøgle.

Det passive live-system (`src/main.py live`, `src/gui.py`) findes stadig som
fallback til ikke-YouTube-kilder.

## Status
- Phase 0 (audio + MIDI plumbing) ✅
- Phase 1 (key detection, 4/4 on test) ✅
- Phase 2 (realtime pipeline + smoothing) ✅
- Phase 3 (MIDI output) ✅ code — pending live UAD confirmation
- Phase 4 (GUI status + log + manual override) ✅
- Phase 5 (robustness, config) — partial (config.json exists)
