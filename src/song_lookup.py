"""Titel-opslag — hent sang fra YouTube-tab og slå toneart op i bibliotek.

To dele:
  1. chrome_title()    -> aktiv Chrome-tab-titel via AppleScript.
  2. clean_title()     -> strip "(Karaoke Version)", "- YouTube", osv. -> (artist, title).
  3. lookup_key()      -> MusicBrainz (titel->MBID) + AcousticBrainz (MBID->toneart).

Bruges som HYBRID PRIOR: lås CC#16 straks fra bibliotek mens lyd-buffer fylder.
Lyd-detektion er ground truth — overruler hvis uenig (karaoke ofte transponeret).

Kilde: MusicBrainz + AcousticBrainz. GRATIS, ingen API-nøgle. (GetSongBPM droppet
— deres API er bag Cloudflare bot-challenge, ubrugelig fra script.) MusicBrainz
kræver en User-Agent med kontakt-email (config song_lookup.contact_email).
AcousticBrainz har kun toneart for sange andre har analyseret (god dækning på hits,
huller på nyt/obskurt). Read-only projekt, men data serveres stadig.

CLI:
  python src/song_lookup.py title          # vis renset titel fra Chrome
  python src/song_lookup.py lookup          # fuld: titel -> toneart
  python src/song_lookup.py lookup "artist - song"   # manuelt opslag
"""
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Note-navn (med b/#) -> pitch class. Enharmoniske dækket.
_NOTE_PC = {
    "C": 0, "B#": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3,
    "E": 4, "FB": 4, "F": 5, "E#": 5, "F#": 6, "GB": 6, "G": 7,
    "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11, "CB": 11,
}

CONFIG = os.path.join(os.path.dirname(__file__), "..", "config.json")

# Ord/parenteser der fjernes fra YouTube-titel.
_JUNK_WORDS = re.compile(
    r"\b(karaoke|instrumental|backing\s*track|lyrics?|official|audio|video|"
    r"hd|4k|mv|version|cover|remaster(?:ed)?|with\s*lyrics|no\s*vocals?|"
    r"sing\s*along|playback|minus\s*one|youtube)\b",
    re.I,
)
_PARENS = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")  # (..) [..] {..}


@dataclass
class KeyHint:
    artist: str
    title: str
    pitch_class: int        # 0..11 root
    mode: str               # "major" | "minor"
    relative_major_pc: int  # minor -> +3; til CC#16 (samme som lyd-pipeline)
    key_str: str            # rå streng fra DB, fx "F major"
    strength: float = 0.0   # AcousticBrainz key_strength 0..1 (tillid)
    source: str = "acousticbrainz"


def chrome_title():
    """Aktiv Chrome-tab-titel. None hvis Chrome lukket / fejl."""
    try:
        out = subprocess.run(
            ["osascript", "-e",
             'tell application "Google Chrome" to return title of active tab of front window'],
            capture_output=True, text=True, timeout=4,
        )
        t = out.stdout.strip()
        return t or None
    except Exception:
        return None


def clean_title(raw):
    """YouTube-titel -> (artist|None, title). Strip suffixer, parenteser, junk."""
    if not raw:
        return None, ""
    base = re.sub(r"\s*-\s*YouTube\s*$", "", raw, flags=re.I)  # strip suffix FOER split
    t = _PARENS.sub(" ", base)                             # fjern (...) [...]
    t = _JUNK_WORDS.sub(" ", t)                            # fjern løse junk-ord
    t = re.sub(r"[|–—]+", " ", t)                          # pipes/dashes -> space
    t = re.sub(r"\s+", " ", t).strip(" -·")
    # "Artist - Title" split paa foerste rene bindestreg.
    m = re.split(r"\s-\s", base)
    artist = None
    if len(m) >= 2:
        artist = _clean_part(m[0])
        title = _clean_part(" ".join(m[1:]))
    else:
        title = t
    return (artist or None), title.strip()


def _clean_part(s):
    s = re.sub(r"\s*-\s*YouTube\s*$", "", s, flags=re.I)
    s = _PARENS.sub(" ", s)
    s = _JUNK_WORDS.sub(" ", s)
    s = re.sub(r"[|–—]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" -·")


def parse_key(key_str):
    """DB-key-streng (fx 'Am', 'F#', 'Db minor') -> (pitch_class, mode)."""
    if not key_str:
        return None
    s = key_str.strip()
    m = re.match(r"^([A-Ga-g])([#b]?)", s)
    if not m:
        return None
    root = (m.group(1) + (m.group(2) or "")).upper()
    pc = _NOTE_PC.get(root)
    if pc is None:
        return None
    rest = s[m.end():].lower()
    minor = ("m" in rest and "maj" not in rest) or "min" in rest
    mode = "minor" if minor else "major"
    return pc, mode


def _config():
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except Exception:
        return {}


_SKIP_TITLE = re.compile(r"\b(remix|live|karaoke|instrumental|acoustic|demo|edit)\b", re.I)


def _get_json(url, ua, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def mb_search(artist, title, ua):
    """MusicBrainz: titel(+artist) -> liste af (mbid, title, artist), bedste først."""
    q = f'recording:"{title}"'
    if artist:
        q += f' AND artist:"{artist}"'
    url = "https://musicbrainz.org/ws/2/recording/?" + urllib.parse.urlencode(
        {"query": q, "fmt": "json", "limit": 8})
    try:
        d = _get_json(url, ua)
    except Exception as e:
        print(f"(MusicBrainz-fejl: {e})", file=sys.stderr)
        return []
    out = []
    for rec in d.get("recordings", []):
        nm = rec.get("title", "")
        ac = rec.get("artist-credit", [{}])[0].get("name", "")
        out.append((rec["id"], nm, ac, _SKIP_TITLE.search(nm) is None))
    # original-versioner (uden remix/live/karaoke) først, behold MB's score-rækkefølge ellers.
    out.sort(key=lambda x: 0 if x[3] else 1)
    return out


def ab_key(mbid, ua):
    """AcousticBrainz low-level -> (key_key, key_scale, strength) eller None."""
    url = f"https://acousticbrainz.org/api/v1/{mbid}/low-level"
    try:
        d = _get_json(url, ua)
    except Exception:
        return None  # ofte 404 = ingen analyse for denne MBID
    t = d.get("tonal", {})
    k = t.get("key_key")
    if not k:
        return None
    return k, t.get("key_scale", "major"), float(t.get("key_strength", 0.0))


def _try_order(artist, title, ua, min_strength):
    cands = mb_search(artist, title, ua)
    for mbid, nm, ac, _orig in cands[:6]:
        res = ab_key(mbid, ua)
        if not res:
            continue
        key_key, key_scale, strength = res
        if strength < min_strength:
            continue
        parsed = parse_key(f"{key_key} {key_scale}")
        if not parsed:
            continue
        pc, mode = parsed
        relmaj = pc if mode == "major" else (pc + 3) % 12
        return KeyHint(
            artist=ac or (artist or ""), title=nm or title,
            pitch_class=pc, mode=mode, relative_major_pc=relmaj,
            key_str=f"{key_key} {key_scale}", strength=strength,
        )
    return None


def lookup_key(artist, title):
    """Titel -> KeyHint via MusicBrainz + AcousticBrainz. None hvis intet fund.

    YouTube-titel-rækkefølge er tvetydig ("Artist - Titel" vs "Titel - Artist"),
    så prøv begge når der er en artist-del."""
    cfg = _config().get("song_lookup", {})
    ua = f"AL_KEY_DETECTOR/1.0 ( {cfg.get('contact_email', 'unknown')} )"
    min_strength = float(cfg.get("min_strength", 0.0))
    h = _try_order(artist, title, ua, min_strength)
    if h is None and artist:
        h = _try_order(title, artist, ua, min_strength)  # ombyttet rækkefølge
    return h


def hint_from_chrome():
    """Fuld kæde: Chrome-titel -> rens -> opslag. Returnér KeyHint eller None."""
    raw = chrome_title()
    if not raw:
        return None
    artist, title = clean_title(raw)
    if not title:
        return None
    return lookup_key(artist, title)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "title"
    if cmd == "title":
        raw = chrome_title()
        print(f"rå:    {raw}")
        artist, title = clean_title(raw or "")
        print(f"artist: {artist}\ntitle:  {title}")
    elif cmd == "lookup":
        if len(sys.argv) > 2:
            artist, title = clean_title(sys.argv[2])
        else:
            raw = chrome_title()
            artist, title = clean_title(raw or "")
            print(f"rå Chrome-titel: {raw}")
        print(f"opslag: artist={artist!r} title={title!r}")
        h = lookup_key(artist, title)
        if h:
            print(f"FUND: {h.artist} - {h.title} | key {h.key_str} (strength {h.strength:.2f}) "
                  f"-> {NOTE_NAMES[h.pitch_class]} {h.mode} "
                  f"| send-tone (relmaj) {NOTE_NAMES[h.relative_major_pc]}")
        else:
            print("intet fund (ingen MusicBrainz-match eller ingen AcousticBrainz-analyse).")
    else:
        print(__doc__)
