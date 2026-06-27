import pytest
from youtube_search import search

def test_requires_api_key():
    with pytest.raises(ValueError):
        search("q", "", 5)

def test_parses_results():
    fake = {"items": [
        {"id": {"videoId": "v1"},
         "snippet": {"title": "Song A", "channelTitle": "Chan",
                     "thumbnails": {"medium": {"url": "http://t/1.jpg"}}}}
    ]}
    out = search("q", "KEY", 5, fetcher=lambda url: fake)
    assert out == [{"videoId": "v1", "title": "Song A", "channel": "Chan",
                    "thumbnail": "http://t/1.jpg"}]
