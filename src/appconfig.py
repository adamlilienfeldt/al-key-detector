"""Merget config: config.json (committet) + config.local.json (gitignored secrets)."""
import json, os

CONFIG = os.path.join(os.path.dirname(__file__), "..", "config.json")
CONFIG_LOCAL = os.path.join(os.path.dirname(__file__), "..", "config.local.json")


def _deep_merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_merged_config():
    with open(CONFIG) as f:
        cfg = json.load(f)
    if os.path.exists(CONFIG_LOCAL):
        with open(CONFIG_LOCAL) as f:
            _deep_merge(cfg, json.load(f))
    return cfg


def get_cache_dir(cfg):
    d = os.path.expanduser(cfg.get("player", {}).get("cache_dir", "~/Library/Caches/AL_KEY_DETECTOR"))
    os.makedirs(d, exist_ok=True)
    return d
