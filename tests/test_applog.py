import json
from applog import log_event

def test_appends_jsonl_with_ts_and_fields(tmp_path):
    p = tmp_path / "events.jsonl"
    log_event("key", path=str(p), t=12.5, pc=7)
    log_event("load", path=str(p), video_id="abc")
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 2
    a = json.loads(lines[0]); b = json.loads(lines[1])
    assert a["type"] == "key" and a["t"] == 12.5 and a["pc"] == 7 and "ts" in a
    assert b["type"] == "load" and b["video_id"] == "abc"
