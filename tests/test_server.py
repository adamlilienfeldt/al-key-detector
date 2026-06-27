from fastapi.testclient import TestClient
import server
from timeline import Timeline, Segment

def setup_function(_):
    server.STATE.update({"timeline": None, "driver": None, "video_id": None})

class _FakeSink:
    def send_key(self, pc): pass
    def set_retune(self, on): pass
    def close(self): pass

def test_search_no_key(monkeypatch):
    monkeypatch.setattr(server, "CFG", {"youtube": {"search_max_results": 5}})  # no api_key
    c = TestClient(server.app)
    r = c.get("/api/search", params={"q": "abba"})
    assert r.status_code == 200
    assert "error" in r.json()

def test_load_builds_and_stores_timeline(monkeypatch):
    segs = [Segment(0, 10, 0, "C", "major", 0.7), Segment(10, 20, 7, "G", "major", 0.7)]
    monkeypatch.setattr(server, "build_timeline", lambda vid: Timeline(segs))
    monkeypatch.setattr(server, "make_sink", lambda: _FakeSink())
    c = TestClient(server.app)
    r = c.post("/api/load", json={"videoId": "abc"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert [s["relative_major_pc"] for s in body["segments"]] == [0, 7]
    assert server.STATE["video_id"] == "abc"

def test_timeline_404_when_absent():
    c = TestClient(server.app)
    assert c.get("/api/timeline/nope").status_code == 404
