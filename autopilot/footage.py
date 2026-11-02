"""Finds and downloads vertical stock clips from Pexels for each scene."""
from pathlib import Path

import requests

from .config import env

API = "https://api.pexels.com/videos/search"
FALLBACK_QUERIES = ["dark clouds sky", "night city lights", "forest fog", "ocean waves night", "candle dark"]


def _search(query: str, key: str, page: int = 1) -> list[dict]:
    r = requests.get(
        API,
        headers={"Authorization": key},
        params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 15, "page": page},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("videos", [])


def _best_file(video: dict) -> dict | None:
    files = [
        f for f in video.get("video_files", [])
        if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")
        and f["height"] > f["width"] and f["width"] >= 720
    ]
    if not files:
        return None
    # closest to 1080 wide, avoid huge 4K downloads
    return min(files, key=lambda f: abs(f["width"] - 1080))


def find_clip(query: str, min_seconds: float, used: set, key: str) -> tuple[dict, dict]:
    for q in [query, " ".join(query.split()[:2])] + FALLBACK_QUERIES:
        for page in (1, 2):
            for video in _search(q, key, page):
                if video["id"] in used:
                    continue
                if video.get("duration", 0) < min(min_seconds, 6):
                    continue
                f = _best_file(video)
                if f:
                    return video, f
    raise RuntimeError(f"No usable footage found for '{query}'")


def download(url: str, out: Path) -> Path:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(out, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    return out


def get_scene_clips(scenes: list[dict], durations: list[float], history: dict, work: Path) -> list[dict]:
    key = env("PEXELS_API_KEY")
    used = set(history.get("used_footage", []))
    clips = []
    for i, (scene, dur) in enumerate(zip(scenes, durations)):
        video, f = find_clip(scene["search"], dur, used, key)
        used.add(video["id"])
        path = download(f["link"], work / f"clip_{i:02d}.mp4")
        clips.append({
            "path": path,
            "pexels_id": video["id"],
            "author": (video.get("user") or {}).get("name", "Pexels"),
            "duration": video.get("duration", 0),
        })
    return clips
