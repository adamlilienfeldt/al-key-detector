"""Hent YouTube-lyd (yt-dlp) + cache pr. video_id. Loader/runner injicerbar (test)."""
import glob
import os
import subprocess

import librosa


def fetch_audio(video_id, cache_dir, *, runner=subprocess.run, loader=librosa.load, sr=22050):
    os.makedirs(cache_dir, exist_ok=True)
    existing = glob.glob(os.path.join(cache_dir, f"{video_id}.*"))
    if not existing:
        target = os.path.join(cache_dir, f"{video_id}.%(ext)s")
        cmd = ["yt-dlp", "-f", "bestaudio", "--no-playlist",
               "-o", target, f"https://www.youtube.com/watch?v={video_id}"]
        r = runner(cmd, capture_output=True, text=True)
        if getattr(r, "returncode", 1) != 0:
            raise RuntimeError(f"yt-dlp fejl: {getattr(r, 'stderr', '')[:300]}")
        existing = glob.glob(os.path.join(cache_dir, f"{video_id}.*"))
        if not existing:
            raise RuntimeError("yt-dlp: ingen lyd-fil produceret")
    y, out_sr = loader(existing[0], sr=sr, mono=True)
    return y, out_sr
