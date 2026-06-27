"""YouTube Data API v3 search.list wrapper. API-noegle fra config.local.json."""
import json
import urllib.parse
import urllib.request

_API = "https://www.googleapis.com/youtube/v3/search"


def _http_get_json(url):
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.loads(r.read().decode())


def search(query, api_key, max_results=12, *, fetcher=_http_get_json):
    if not api_key:
        raise ValueError("no api key")
    qs = urllib.parse.urlencode({
        "part": "snippet", "q": query, "type": "video",
        "maxResults": max_results, "key": api_key})
    data = fetcher(f"{_API}?{qs}")
    out = []
    for it in data.get("items", []):
        sn = it.get("snippet", {})
        thumb = sn.get("thumbnails", {}).get("medium", {}).get("url", "")
        out.append({"videoId": it["id"]["videoId"], "title": sn.get("title", ""),
                    "channel": sn.get("channelTitle", ""), "thumbnail": thumb})
    return out
