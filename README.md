# Karaoke Auto-Tune — automatisk toneart-styring

Lytter på Pro Tools-audio (karaoke-instrumental), detekterer toneart i realtid,
og sender MIDI CC#16 (Key) til UAD Auto-Tune via IAC Driver. Scale håndteres via
relativ-major-trick (minor → relativ major), så kun CC#16 bruges.

## Opsætning (engang)

1. **IAC Driver:** Audio MIDI Setup → MIDI Studio → IAC Driver → "Device is online".
   Bekræft port hedder noget med "IAC".
2. **UAD Console:** MIDI-learn CC#16 til Auto-Tune's Key-parameter, kanal 1.
3. **Pro Tools:** rut karaoke-lyd til "Pro Tools Audio Bridge 2-A" (device index 3).
4. Python-miljø:
   ```
   python3.11 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```

Alle settings (device, port, CC, thresholds, key-mapping) ligger i `config.json`.

## Kør

```bash
# Fuld drift: lyt live + send MIDI
PYTHONPATH=src ./venv/bin/python src/main.py live

# Tør-kør (detektér, INGEN MIDI)
PYTHONPATH=src ./venv/bin/python src/main.py live --no-midi

# Test mod en lydfil
PYTHONPATH=src ./venv/bin/python src/main.py file '/sti/sang.mp4' --fast --midi
```

Programmet låser typisk korrekt toneart ~25-40 sek inde i en sang (akkumulerer
fra sang-start). Stilhed mellem sange (≥~8s) nulstiller automatisk til ny sang.

## Værktøjer (Fase 0 / fejlfinding)

```bash
# Audio-devices + MIDI-porte
./venv/bin/python src/list_devices.py

# Find hvilket device har signal (afspil lyd imens)
./venv/bin/python src/audio_capture.py probe

# Send en enkelt tone manuelt til Auto-Tune
./venv/bin/python src/midi_output.py key A

# Detektér toneart i en fil
PYTHONPATH=src ./venv/bin/python src/key_detection.py sang.wav
```

## Titel-prior (hybrid)

Henter aktiv YouTube-titel fra Chrome, slår toneart op via MusicBrainz +
AcousticBrainz, og låser CC#16 **straks** (provisorisk) mens lyd-buffer fylder.
Lyd-detektion er ground truth og overruler (karaoke ofte transponeret). Retune
(CC#18) tændes ALDRIG af prior alene — kun når lyd bekræfter.

Kilde: gratis, ingen API-nøgle. MusicBrainz kræver kun en kontakt-email i
User-Agent (`config.json` → `song_lookup.contact_email`). AcousticBrainz har kun
toneart for sange andre har analyseret — god dækning på hits, huller på nyt/obskurt.
(GetSongBPM droppet: deres API ligger bag Cloudflare bot-challenge, ubrugelig fra
script.) Test:
```bash
./venv/bin/python src/song_lookup.py title     # vis renset Chrome-titel
./venv/bin/python src/song_lookup.py lookup     # titel -> toneart
```

## GUI (Fase 4)

```bash
PYTHONPATH=src ./venv/bin/python src/gui.py
```
Viser YouTube-titel, aktuel send-tone, autotune-status, og en log der opdateres
ved hvert nyt event. 12 knapper sætter toneart manuelt (låser auto til "Auto"
trykkes). Knapper: Auto (slip manuel), Autotune PÅ/FRA (tving retune), Reset sang.

Kræver Tk: `brew install python-tk@3.11` (engang). Kør GUI **eller** `main.py live`
— ikke begge (deler audio-device).

## Status
- Fase 0 (audio+MIDI-rør) ✅
- Fase 1 (key-detection, 4/4 på test) ✅
- Fase 2 (realtids-pipeline + smoothing) ✅
- Fase 3 (MIDI-output) ✅ kode — mangler live UAD-bekræftelse
- Fase 4 (GUI status + log + manuel override) ✅
- Fase 5 (robusthed, config) — delvist (config.json findes)
