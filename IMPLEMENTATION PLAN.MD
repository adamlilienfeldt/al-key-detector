# Implementation Plan: Automatisk Toneart-Styring til UAD Auto-Tune (Karaoke)

## 1. Formål

Bygge et lokalt macOS-program der:
1. Lytter på systemets/Pro Tools' audio-output (karaoke-instrumentalen fra YouTube)
2. Detekterer toneart (key + scale) i realtid via audio-analyse
3. Sender MIDI CC-beskeder via IAC Driver til UAD Console, så Auto-Tune's toneart-parameter følger sangen automatisk
4. Viser et simpelt statusvindue med manuel override, og kører i øvrigt i baggrunden

Brugeren styrer i forvejen UAD Auto-Tune's toneart manuelt via MIDI CC:
- **CC#16** → Key (forventet værdiområde 0–11, svarende til C, C#, D, ... B — skal verificeres i UAD Console's MIDI-learn/mapping)
- **CC#17** → Scale (forventet 0 = major, 1 = minor, eller lignende binær/few-state mapping — skal verificeres)

**VIGTIGT — skal afklares med bruger/ved test, før CC-værdier hardkodes:**
- Den nøjagtige værdi-til-toneart-mapping i UAD Console (er det 0–11 lineært, eller noteret anderledes, f.eks. 0/127-skalering pr. trin?)
- Om scale-CC har flere værdier end major/minor (f.eks. harmonisk minor, mixolydisk osv. — sandsynligvis ikke nødvendigt for karaoke, men bør tjekkes)
- MIDI-kanal Auto-Tune lytter på (default antagelse: kanal 1 / 0-indekseret 0, men kan være sat til andet)

---

## 2. Arkitektur (overblik)

```
┌─────────────────────┐     ┌────────────────────────┐     ┌─────────────────────┐
│ YouTube (browser)    │     │ Pro Tools audio bridge  │     │ Virtuelt audio-     │
│ afspiller karaoke-   │ ──> │ (routes systemlyd til   │ ──> │ device (fx eksist.  │
│ instrumental         │     │ Pro Tools input)         │     │ Pro Tools output/   │
└─────────────────────┘     └────────────────────────┘     │ Aggregate Device)    │
                                                              └──────────┬──────────┘
                                                                         │ optages af
                                                                         ▼
                                                              ┌─────────────────────┐
                                                              │ Python-program       │
                                                              │ (denne plan)         │
                                                              │                      │
                                                              │ 1. Audio capture     │
                                                              │ 2. Key detection     │
                                                              │ 3. Smoothing/        │
                                                              │    confidence-logik  │
                                                              │ 4. MIDI CC sender    │
                                                              │ 5. GUI status/override│
                                                              └──────────┬──────────┘
                                                                         │ MIDI CC#16/17
                                                                         ▼
                                                              ┌─────────────────────┐
                                                              │ IAC Driver (macOS)   │
                                                              └──────────┬──────────┘
                                                                         │
                                                                         ▼
                                                              ┌─────────────────────┐
                                                              │ UAD Console          │
                                                              │ Auto-Tune plugin     │
                                                              └─────────────────────┘
```

**Vigtig forudsætning der skal verificeres tidligt (Fase 0):** at det valgte audio-input device i Python rent faktisk modtager karaoke-instrumental-lyden uden at forstyrre den live mikrofon-signalvej til Auto-Tune. Brugeren har bekræftet at Pro Tools audio bridge allerede router lyden til et device, der kan optages fra — dette skal first verificeres med et simpelt audio-level-test (Fase 0), før noget andet bygges.

---

## 3. Tech stack

| Komponent | Valg | Begrundelse |
|---|---|---|
| Sprog | Python 3.11+ | Hurtig iteration, gode audio/MIDI-biblioteker, kører fint på macOS |
| Audio capture | `sounddevice` (PortAudio binding) | Simpelt cross-platform API, lav latency, device-enumerering indbygget |
| Key detection | `librosa` (chroma features + Krumhansl-Schmuckler-lignende profil-matching) | Industristandard til musikanalyse i Python, velkendt og dokumenteret |
| MIDI output | `mido` + `python-rtmidi` | Standardkombination til at sende MIDI til IAC Driver på macOS |
| GUI | `tkinter` (indbygget i Python) | Ingen ekstra dependency, nok til simpelt statusvindue + dropdown override |
| Packaging | Almindeligt venv + requirements.txt til start. Evt. `pyinstaller` senere hvis det skal være en dobbeltklik-app | Hold det simpelt i første iteration |

**Claude Code skal verificere disse valg ved opstart** (særligt at `sounddevice`/`librosa`/`python-rtmidi` installerer og virker uden problemer på brugerens specifikke macOS-version og chip — Intel vs. Apple Silicon kan give forskellige binære wheel-krav).

---

## 4. Faseplan

### Fase 0 — Verificér audio- og MIDI-rør (gør INGEN detektion endnu)
Mål: bekræft at signalvejen er teknisk mulig, før der bygges logik ovenpå.

- [ ] List alle audio input/output devices synlige for Python (`sounddevice.query_devices()`)
- [ ] Identificér hvilket device der svarer til Pro Tools' audio bridge-output
- [ ] Lav et minimalt script der optager 5 sekunder fra dette device og gemmer som .wav — afspil filen og bekræft det er karaoke-lyden
- [ ] List alle MIDI output-porte synlige for `mido`/`rtmidi` (`mido.get_output_names()`), bekræft "IAC Driver Bus 1" (eller relevant bus) er til stede
- [ ] Send en enkelt test-CC-besked (CC#16, værdi 0) til IAC-porten og bekræft i UAD Console at Auto-Tune reagerer / MIDI-learn-vinduet viser beskeden modtaget
- [ ] Bekræft den faktiske værdi-til-toneart-mapping ved at sende CC#16 med værdier 0, 1, 2... og notere hvilken toneart hvert nummer giver i UAD Console
- [ ] Bekræft CC#17's værdier for major/minor på samme måde

**Exit-kriterie:** Bruger kan bekræfte "ja, jeg hørte karaoke-lyden i den optagede test-fil" OG "ja, Auto-Tune skiftede toneart da jeg sendte test-CC'en manuelt fra scriptet."

---

### Fase 1 — Key detection prototype (offline, ingen MIDI endnu)
Mål: valider at detektionsalgoritmen rent faktisk virker på karaoke-instrumental-lyd (ikke kun på fuld musik med vokal/bas).

- [ ] Implementér chroma-baseret key-detection funktion: tag en lydbuffer (fx 6–10 sekunder), beregn chromagram (`librosa.feature.chroma_cqt` eller `chroma_cens`), match mod major/minor profil-templates, returnér (key, scale, confidence-score)
- [ ] Test funktionen offline på 5-10 forskellige karaoke-instrumental-klip i forskellige genrer (bed bruger om at eksportere korte WAV-klip fra et par typiske sange de bruger)
- [ ] Notér hvor lang en audio-buffer der kræves for stabil/korrekt detektion (forvent at skulle eksperimentere — start med 8 sek, juster op/ned)
- [ ] Notér hvor ofte algoritmen fejler eller er usikker (lav confidence) på rene instrumentaler uden vokal — dette er forventeligt at være sværere end normal musik, og er grunden til at confidence-threshold + manuel override er nødvendig (se Fase 3)

**Exit-kriterie:** Algoritmen rammer korrekt toneart på et tilfredsstillende antal (bruger definerer "tilfredsstillende", fx 70-80%) af testklippene, ELLER der er identificeret en klar justering (anden chroma-metode, længere buffer, etc.) der forbedrer det tilstrækkeligt.

---

### Fase 2 — Realtids-pipeline (audio in → key detection, stadig ingen MIDI)
Mål: kør detektionen kontinuerligt på live audio-strøm i stedet for statiske filer.

- [ ] Implementér rullende audio-buffer (ring buffer) der løbende fyldes fra `sounddevice` input-stream
- [ ] Køre key-detection periodisk (fx hvert 2-3 sekund) på de seneste N sekunder af bufferen
- [ ] Implementér smoothing-logik: kun rapportér en toneart-ændring når samme (key, scale) er blevet detekteret med tilstrækkelig confidence i flere på hinanden følgende analyse-vinduer (undgår "flapper" mellem to toner)
- [ ] Log til konsol: timestamp, detekteret toneart, confidence, om det blev accepteret som "stabilt"

**Exit-kriterie:** Kør pipeline live mod en afspillet karaoke-sang i 2-3 minutter, bekræft konsol-loggen viser en rimelig stabil og korrekt toneart efter opstartsperioden (de første par sekunder forventes usikre, det er ok).

---

### Fase 3 — MIDI-output integration
Mål: koble detektion til faktisk CC-afsendelse.

- [ ] Implementér MIDI-sender der tager (key, scale) og sender CC#16 + CC#17 med korrekt mapping (fra Fase 0's målinger)
- [ ] Kun send MIDI når smoothing-logikken (Fase 2) godkender et stabilt skifte — undgå at spamme CC-beskeder
- [ ] Send kun *ændringer* (ikke gentag samme værdi hele tiden), for at undgå at det visuelt "blinker" i UAD Console eller forstyrrer andre indstillinger
- [ ] Tilføj en lille startup-fase/grace period: ved sang-start, vent til første stabile detektion før noget sendes (undgå tilfældigt CC-spam i intro/stilhed)

**Exit-kriterie:** Afspil en karaoke-sang, bekræft Auto-Tune's toneart i UAD Console rent faktisk skifter til den korrekte toneart automatisk inden for en rimelig opstartstid (fx 10-20 sekunder).

---

### Fase 4 — GUI: status + manuel override
Mål: minimalt, ikke-intrusivt vindue der kører i baggrunden, men giver tryghed og kontrol.

- [ ] Lille altid-ovenpå (eller dock-bar) Tkinter-vindue der viser:
  - Nuværende detekteret toneart + scale
  - Confidence-niveau (evt. som farve: rød/gul/grøn)
  - Seneste 5-10 log-linjer (skifte-historik)
- [ ] Dropdown/knapper til manuel override: brugeren kan vælge toneart + scale direkte, som sender CC øjeblikkeligt og **pauser auto-detektion** indtil brugeren slår den til igen (vigtigt — automatik skal ikke overskrive en manuel rettelse midt i en sang)
- [ ] Knap til at "genoptage automatisk detektion" efter manuel override
- [ ] Knap til start/stop af hele lytte-pipelinen (fx hvis der skal være pause mellem sange)

**Exit-kriterie:** Bruger kan køre en hel karaoke-session, se status i vinduet, og uden besvær overstyre manuelt hvis algoritmen gætter forkert — uden at automatikken "kæmper" mod den manuelle rettelse.

---

### Fase 5 — Robusthed og kantsager
Mål: gøre det production-ready til faktisk brug på en aften med gæster.

- [ ] Håndter at audio-device forsvinder/genstartes (fx Pro Tools genstartes midt i en session) uden at hele programmet crasher — vis fejl i GUI, tillad reconnect uden at genstarte appen
- [ ] Håndter MIDI-port der ikke findes ved opstart (fx IAC ikke aktiveret) — tydelig fejlmeddelelse, ikke silent fail
- [ ] Håndter stilhed/meget lavt lydniveau (mellem sange, eller hvis nogen sætter på pause) — algoritmen skal ikke detektere en tilfældig "toneart" på baggrundsstøj eller stilhed; tilføj et minimum-lydniveau-tjek før detektion køres
- [ ] Tilføj simpel konfigurationsfil (JSON/YAML) til: device-navne, CC-numre, MIDI-kanal, confidence-threshold, smoothing-vinduestørrelse — så det kan justeres uden kodeændring
- [ ] Skriv en kort README med opstartsinstruktioner (hvilket device skal vælges, hvordan startes programmet, hvad gør man hvis det går i stå)

**Exit-kriterie:** Programmet kan startes, køre en hel session, og lukkes ned uden manuel indgriben i koden — kun via GUI/konfigurationsfil.

---

## 5. Åbne spørgsmål Claude Code bør stille/afklare med brugeren tidligt

1. Det eksakte audio-device-navn der svarer til Pro Tools' bridge-output (find via device-listing i Fase 0)
2. Den faktiske CC-værdi-til-toneart-mapping i UAD Console (kan ikke gættes, skal måles — se Fase 0)
3. Hvor mange sekunder "opstartstid" er acceptabelt før første toneart-skift sendes (påvirker buffer-størrelse/smoothing)
4. Om der er flere instanser af Auto-Tune (fx flere mikrofoner/kanaler) der alle skal modtage samme CC, eller kun én
5. Om brugeren ønsker programmet pakket som en dobbeltklik-app (`pyinstaller`) til sidst, eller er tilfreds med at køre det fra terminal/Claude Code under sessioner

---

## 6. Foreslået repo-struktur

```
karaoke-autotune/
├── README.md
├── requirements.txt
├── config.json                  # CC-numre, device-navne, thresholds
├── src/
│   ├── audio_capture.py         # sounddevice ring buffer
│   ├── key_detection.py         # librosa chroma + profile matching
│   ├── smoothing.py             # stabilitets-/confidence-logik
│   ├── midi_output.py           # mido/rtmidi CC sender
│   ├── gui.py                   # tkinter statusvindue + override
│   └── main.py                  # sammenkobler det hele
└── tests/
    ├── sample_clips/             # korte WAV-eksempler til Fase 1-test
    └── test_key_detection.py
```

---

## 7. Rækkefølge-anbefaling til Claude Code

Byg og test strengt i fase-rækkefølge (0 → 5). Spring ikke til GUI eller MIDI før Fase 0 og Fase 1 er bekræftet at virke isoleret — fejlfinding er markant nemmere når audio-capture, key-detection og MIDI-output er valideret hver for sig, før de kobles sammen.