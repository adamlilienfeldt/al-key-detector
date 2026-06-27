import json, os
from appconfig import load_merged_config, get_cache_dir

def _write(p, d):
    with open(p, "w") as f: json.dump(d, f)

def test_local_overrides_and_merges(tmp_path, monkeypatch):
    base = tmp_path / "config.json"; local = tmp_path / "config.local.json"
    _write(base, {"youtube": {"api_key": "", "search_max_results": 12}, "midi": {"cc_key": 16}})
    _write(local, {"youtube": {"api_key": "SECRET"}})
    monkeypatch.setattr("appconfig.CONFIG", str(base))
    monkeypatch.setattr("appconfig.CONFIG_LOCAL", str(local))
    cfg = load_merged_config()
    assert cfg["youtube"]["api_key"] == "SECRET"        # local wins
    assert cfg["youtube"]["search_max_results"] == 12     # base preserved
    assert cfg["midi"]["cc_key"] == 16                    # untouched section

def test_cache_dir_created(tmp_path):
    d = get_cache_dir({"player": {"cache_dir": str(tmp_path / "c")}})
    assert os.path.isdir(d)
