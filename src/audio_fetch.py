"""Hent YouTube-video+lyd (yt-dlp) + cache pr. video_id. Samme fil bruges til
afspilning (serveres af backend) OG tidslinje-analyse. Loader/runner injicerbar (test)."""
import glob
import os
import subprocess

import librosa

# Progressiv mp4 (video+lyd i én fil) hvis muligt, ellers bedste samlede.
_FORMAT = "best[ext=mp4]/best"


def media_glob(video_id, cache_dir):
    return glob.glob(os.path.join(cache_dir, f"{video_id}.*"))


def fetch_media_file(video_id, cache_dir, *, runner=subprocess.run):
    """Download video+lyd til cache (eller genbrug). Returnér sti til fil."""
    os.makedirs(cache_dir, exist_ok=True)
    existing = media_glob(video_id, cache_dir)
    if existing:
        return existing[0]
    target = os.path.join(cache_dir, f"{video_id}.%(ext)s")
    cmd = ["yt-dlp", "-f", _FORMAT, "--no-playlist",
           "-o", target, f"https://www.youtube.com/watch?v={video_id}"]
    r = runner(cmd, capture_output=True, text=True)
    if getattr(r, "returncode", 1) != 0:
        raise RuntimeError(f"yt-dlp fejl: {getattr(r, 'stderr', '')[:300]}")
    existing = media_glob(video_id, cache_dir)
    if not existing:
        raise RuntimeError("yt-dlp: ingen fil produceret")
    return existing[0]


def fetch_audio(video_id, cache_dir, *, runner=subprocess.run, loader=librosa.load, sr=22050):
    """Sikr media-fil + load lyden mono ved sr (til tidslinje-analyse)."""
    path = fetch_media_file(video_id, cache_dir, runner=runner)
    y, out_sr = loader(path, sr=sr, mono=True)
    return y, out_sr
