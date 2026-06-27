"""Hent YouTube-video+lyd (yt-dlp) + cache pr. video_id. Samme fil bruges til
afspilning (serveres af backend) OG tidslinje-analyse. Loader/runner injicerbar (test)."""
import glob
import os
import subprocess
import sys

import librosa

# Tving H.264 (avc1) video + AAC lyd, merget til mp4 -> universelt afspilleligt i
# browserens <video> (VP9/AV1 vises ikke i Safari). Fallback: progressiv itag 18.
_FORMAT = "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4][vcodec^=avc1]/18/b"
_MERGE_FORMAT = "mp4"


def media_glob(video_id, cache_dir):
    return glob.glob(os.path.join(cache_dir, f"{video_id}.*"))


def fetch_media_file(video_id, cache_dir, *, runner=subprocess.run):
    """Download video+lyd til cache (eller genbrug). Returnér sti til fil."""
    os.makedirs(cache_dir, exist_ok=True)
    existing = media_glob(video_id, cache_dir)
    if existing:
        return existing[0]
    target = os.path.join(cache_dir, f"{video_id}.%(ext)s")
    # Kald yt-dlp som modul med samme interpreter -> uafhaengig af PATH.
    cmd = [sys.executable, "-m", "yt_dlp", "-f", _FORMAT,
           "--merge-output-format", _MERGE_FORMAT, "--no-playlist",
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
