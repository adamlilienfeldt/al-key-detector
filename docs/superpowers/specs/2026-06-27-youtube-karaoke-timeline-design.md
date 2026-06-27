# YouTube karaoke-afspiller med toneart-tidslinje — design

**Dato:** 2026-06-27
**Status:** godkendt design, afventer implementerings-plan

## Problem

Nuværende system lytter passivt (Chrome afspiller → BlackHole-loopback → live key-detektion)
og antager **én toneart per sang** (accumulate-fra-start). Det fejler ved **modulationer
midt i sang** (slut-kor-løft, bro i anden toneart osv.): det akkumulerede signal udvander
et sent skift, og anti-flap-logikken modarbejder bevidst et ægte skift. Live-detektion har
desuden uundgåeligt lag (det tager sekunder at genkende en ny toneart efter den starter).

## Mål

- Følg **ethvert vedvarende toneart-skift** midt i sang, begge retninger, hvor som helst.
- **Nul detektions-lag:** kend hele sangens toneart-forløb på forhånd og skift CC#16 *før*
  modulationen rammer (look-ahead ~0,5–1s).
- Vise **video med lyrics** (karaoke).
- Vælg sang via **søgning** i app'en (YouTube Data API).
- **Behold det nuværende passiv-system som fallback/beta** (andre kilder end YouTube).

## Kerneidé

I stedet for live-detektion: **hent sangens lyd på forhånd, analysér hele sporet offline til
en toneart-tidslinje**, og afspil videoen i en afspiller hvor vi kender playhead-positionen
præcist. Tidslinjen + kendt position → look-ahead trivielt, alle modulationer dækket, ingen lag.

Sync-problemet (at vide hvor i sangen vi er) løses ved at **app'en selv afspiller** via en
indlejret YouTube IFrame-player, som rapporterer `getCurrentTime()`.

## Arkitektur

Lokal web-app: Python backend + browser frontend. YouTube IFrame-afspilning virker bedst i
en rigtig browser, og det giver søge-/afspiller-interfacet "gratis" uden native webview.

```
┌─ Browser (frontend) ───────────────┐      ┌─ Python backend ──────────────┐
│  Søgefelt + resultater (thumbs)    │──────▶│  YouTube Data API (søg)        │
│  YouTube IFrame-player (video)     │      │  yt-dlp (hent KUN lyd)         │
│  Status: key / autotune / tidslinje│◀────▶│  Offline tidslinje-analyse     │
│  rapporterer playhead (currentTime)│  ws  │  (genbruger key_detection.py)  │
│  manuelle key-knapper (parity)     │      │  Tidslinje→MIDI m. look-ahead  │
└────────────────────────────────────┘      │  (genbruger midi_output.py)    │
                                             └───────────────────────────────┘
                                                          │ CC#16 / CC#18
                                                          ▼  IAC → UAD Auto-Tune
```

## Komponenter

Hver enhed har ét ansvar og kan testes isoleret.

### 1. Backend-server (`src/server.py`)
Async web-server (FastAPI + uvicorn). Serverer frontend, REST til søg/load, websocket til
realtids position↔key.
- `GET /` → frontend.
- `GET /api/search?q=` → proxy YouTube Data API `search.list`, returnér
  `[{videoId, title, channel, thumbnail}]`.
- `POST /api/load {videoId}` → start lyd-fetch + tidslinje-analyse (async job), returnér status.
- `GET /api/timeline/{videoId}` → cached tidslinje hvis klar.
- `WS /ws` → frontend sender `{type:"position", t}`; backend sender `{type:"key",...}` /
  `{type:"status",...}`.

### 2. Søge-modul (`src/youtube_search.py`)
Wrapper om YouTube Data API v3 `search.list`. API-nøgle fra config. Håndterer kvote-/nøgle-fejl
pænt. **Fase B** (kræver API-nøgle).

### 3. Lyd-fetch (`src/audio_fetch.py`)
`yt-dlp -f bestaudio` → temp-fil → `librosa.load(sr=22050, mono=True)`. **Cache pr. videoId**
(undgå gen-download) i `cache_dir`. Returnér samples + samplerate.

### 4. Tidslinje-analyse (`src/timeline.py`)
Segmenteret key-detektion over hele sporet:
- Glidende vindue (default 8s, hop 1s) → `detect_key` pr. vindue → `(t_center, relmaj_pc, conf, margin)`.
- Segmentér: median-filtrér pc-sekvensen, slå runs sammen; en segment-grænse kræver at den nye
  pc er **vedvarende ≥ `min_segment_seconds`** (default 6s) med conf over tærskel.
- Lav-conf vinduer (instrumental/stilhed) → arv nabo eller markér `unknown`.
- Output: ordnet liste `[{start, end, relative_major_pc, key, mode, conf}]`.
- Rent deterministisk → testbar på fil.

### 5. Tidslinje→MIDI-driver (`src/timeline_driver.py`)
Givet playhead `t` (fra frontend): `target = timeline.lookup(t + lookahead_seconds)`.
Ved ændring → `send_key` CC#16. CC#18 (retune): **ON når key er kendt** (offline-analyse er
sikker), OFF i `unknown`-segmenter. Ingen smoother nødvendig (tidslinjen er allerede stabil).
Genbruger `midi_output.py` + `cc_key_map`. Manuel override (GUI-knapper) kan låse key som nu.

### 6. Frontend (`src/web/index.html` + `app.js`)
Én side:
- Søgefelt + resultat-grid (thumbnails). [Fase B]
- YouTube IFrame Player API; ved valg: cue + autoplay.
- Poll `player.getCurrentTime()` ~4×/sek → send via ws.
- Håndtér player-state (play/pause/seek/ended).
- Status-panel: aktuel key, autotune on/off, "tidslinje klar"-indikator, manuelle key-knapper
  + Auto / Autotune PÅ-FRA / Reset (parity med nuværende GUI).

### 7. Fallback-mode (eksisterende system)
`realtime.py` / `main.py` / `gui.py` (passiv live-detektion via BlackHole/Chrome) **bevares
uændret** som separat "Live/beta"-mode — til kilder der ikke er YouTube (Spotify, CD, mic).
Delt kode: `key_detection.py`, `midi_output.py`, `cc_key_map`, `config.json`.

## Data-flow (tidslinje-mode)

```
søg → vælg videoId → POST /load
  → backend: cache-tjek → yt-dlp lyd → timeline.analyse → cache + "ready"
  → frontend: afspil video (IFrame)
  → ws: position-stream (t) ──▶ driver: lookup(t + lookahead) ──▶ MIDI CC#16/CC#18
```

**Frontend er sandheds-kilde for position** (`getCurrentTime`). Seek = position springer →
driver slår op igen → korrekt. Pause = position fryser → driver holder. Ended → idle.

## Start-latency

Video kan starte med det samme; MIDI engagerer når tidslinjen er klar (typisk inden for første
vers: download ~2–8s + analyse hurtigere-end-realtid ~2–5s for 4-min spor). Status viser
"analyserer…". Optimering: start analyse ved **valg** (før play) for at varme op. Indtil
tidslinjen er klar kan eksisterende **titel-prior** (MusicBrainz/AcousticBrainz) sætte en
foreløbig key.

## Config-tilføjelser

```jsonc
"youtube":  { "api_key": "", "search_max_results": 12 },
"player":   { "lookahead_seconds": 0.7,
              "cache_dir": "~/Library/Caches/AL_KEY_DETECTOR" },
"timeline": { "window_seconds": 8, "hop_seconds": 1.0,
              "min_segment_seconds": 6, "conf_threshold": 0.40 }
```
Tom `api_key` → søgning deaktiveret, UI viser "Tilføj API-nøgle". Nøgle holdes lokalt
(ikke committet — `.gitignore` eller separat lokal config).

## Afhængigheder (nye)

`yt-dlp`, `ffmpeg` (yt-dlp lyd-ekstraktion), `fastapi` + `uvicorn`, `websockets`.
`librosa` findes allerede.

## Fejlhåndtering

- Ingen API-nøgle → søge-UI viser prompt; URL-indsæt virker stadig (Fase A).
- Kvote opbrugt → venlig besked.
- yt-dlp-fejl (geo-blok/fjernet video) → besked + foreslå andet resultat eller live-fallback.
- Analyse-fejl / for kort spor → ét-segment-default eller live-fallback.
- IFrame kan ikke afspille (embedding slået fra af uploader) → besked + foreslå andet resultat.

## Test

- **Tidslinje-analyse:** unit-test på kendte filer — statisk-key sang → 1 segment; modulerende
  spor → ≥2 segmenter ved rigtige tidspunkter. Brug `tests/sample_clips`.
- **Søgning:** mock API-svar.
- **Driver:** syntetisk position-stream + tidslinje → assert CC#16-sends + look-ahead-timing.
- **E2E manuel:** rigtig video, sammenlign MIDI-log mod playhead.

## Faser

- **Fase A (kerne):** backend-skelet + **URL-indsæt** (ingen søgning) + tidslinje + IFrame-player
  + driver. Beviser look-ahead/modulations-følgning uden API-nøgle.
- **Fase B:** YouTube Data API søge-UI (kræver nøgle).
- **Fase C:** manuel-override-parity, polish, caching-finpudsning.
- Eksisterende live-mode bevares som fallback hele vejen.

## YAGNI / afgrænsning

- Ingen video-download (kun lyd til analyse; video via IFrame).
- Ingen multi-bruger/server-deployment — kun lokal.
- Ingen offline-DB af tidslinjer ud over simpel fil-cache pr. videoId.
- Ingen automatisk genkendelse af afspilning fra ekstern browser i denne mode (det er
  fallback-systemets domæne).
```
