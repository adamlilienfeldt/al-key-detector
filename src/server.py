"""Lokal web-app backend: soeg, load (byg tidslinje), websocket (position -> MIDI)."""
import json
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from appconfig import load_merged_config, get_cache_dir
from audio_fetch import fetch_audio, media_glob
from timeline import detect_windows, consolidate_related, segment_windows, Timeline
from timeline_driver import TimelineDriver, MidiSink
from key_detection import NOTE_NAMES
import applog
import youtube_search

CFG = load_merged_config()
WEB = os.path.join(os.path.dirname(__file__), "web")
_logp = CFG.get("player", {}).get("log_path")
LOGP = os.path.expanduser(_logp) if _logp else None  # None -> applog default
app = FastAPI()
STATE = {"timeline": None, "driver": None, "video_id": None}


def _log(event_type, **fields):
    applog.log_event(event_type, path=LOGP, **fields)


def _note(pc):
    return None if pc is None else NOTE_NAMES[pc]


def make_sink():
    return MidiSink(CFG)


def build_timeline(video_id):
    cache = get_cache_dir(CFG)
    y, sr = fetch_audio(video_id, cache, sr=int(CFG["detection"]["analysis_samplerate"]))
    t = CFG["timeline"]
    windows = detect_windows(y, sr, window_seconds=t["window_seconds"],
                             hop_seconds=t["hop_seconds"], conf_threshold=t["conf_threshold"])
    # Instrumentering: log RÅ per-vindue-detektioner til at designe udglatning.
    _log("windows", video_id=video_id, hop=t["hop_seconds"],
         w=[[round(w.t, 1), w.relative_major_pc, _note(w.relative_major_pc), round(w.confidence, 2)]
            for w in windows])
    ws = (consolidate_related(windows, t.get("consolidate_dominance", 0.6))
          if t.get("consolidate_related", True) else windows)
    return Timeline(segment_windows(ws, t["hop_seconds"], t["min_segment_seconds"]))


def _segs_json(tl):
    return [{"start": s.start, "end": s.end, "relative_major_pc": s.relative_major_pc,
             "key": s.key, "mode": s.mode, "confidence": s.confidence} for s in tl.segments]


@app.get("/api/search")
def api_search(q: str):
    key = CFG.get("youtube", {}).get("api_key", "")
    mx = CFG.get("youtube", {}).get("search_max_results", 12)
    try:
        return {"items": youtube_search.search(q, key, mx)}
    except ValueError:
        return {"error": "Ingen API-noegle. Tilfoej youtube.api_key i config.local.json."}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/load")
async def api_load(body: dict):
    vid = body.get("videoId")
    if not vid:
        return JSONResponse({"error": "mangler videoId"}, status_code=400)
    tl = build_timeline(vid)
    if STATE["driver"] is None:
        STATE["driver"] = TimelineDriver(tl, make_sink(), CFG["player"]["lookahead_seconds"])
    else:
        STATE["driver"].timeline = tl
        STATE["driver"].last_pc = None
    STATE["timeline"] = tl
    STATE["video_id"] = vid
    _log("load", video_id=vid,
         segments=[{"start": round(s.start, 2), "pc": s.relative_major_pc,
                    "note": _note(s.relative_major_pc), "key": s.key, "mode": s.mode}
                   for s in tl.segments])
    return {"status": "ready", "segments": _segs_json(tl)}


def media_path(video_id):
    hits = media_glob(video_id, get_cache_dir(CFG))
    return hits[0] if hits else None


@app.get("/media/{video_id}")
def media(video_id: str):
    p = media_path(video_id)
    if not p:
        return JSONResponse({"error": "ikke fundet"}, status_code=404)
    return FileResponse(p)


@app.get("/api/timeline/{video_id}")
def api_timeline(video_id: str):
    if STATE["video_id"] != video_id or STATE["timeline"] is None:
        return JSONResponse({"error": "ikke fundet"}, status_code=404)
    return {"segments": _segs_json(STATE["timeline"])}


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    try:
        while True:
            msg = json.loads(await sock.receive_text())
            d = STATE["driver"]
            if msg.get("type") == "position" and d:
                t = float(msg["t"])
                before_pc, before_rt = d.last_pc, d.sink_retune()
                d.on_position(t)
                if d.last_pc != before_pc:
                    _log("key", t=round(t, 2), pc=d.last_pc, note=_note(d.last_pc))
                if d.sink_retune() != before_rt:
                    _log("retune", t=round(t, 2), on=d.sink_retune())
                await sock.send_text(json.dumps({
                    "type": "state", "pc": d.last_pc, "retune": d.sink_retune()}))
            elif msg.get("type") == "manual" and d:
                d.set_manual_key(int(msg["pc"]))
                _log("manual", pc=int(msg["pc"]), note=_note(int(msg["pc"])))
            elif msg.get("type") == "auto" and d:
                d.clear_manual()
                _log("auto")
    except WebSocketDisconnect:
        pass


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"))


@app.get("/app.js")
def appjs():
    return FileResponse(os.path.join(WEB, "app.js"))


@app.get("/style.css")
def style():
    return FileResponse(os.path.join(WEB, "style.css"))
