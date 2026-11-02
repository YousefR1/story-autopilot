"""Sends the finished video to TikTok with the Content Posting API.

mode "inbox":  the video lands in your TikTok inbox as a draft; you tap Post in the app.
mode "direct": the video is published by itself (requires TikTok to have audited your app).
"""
import os
import subprocess
import time
from pathlib import Path

import requests

from .config import env

API = "https://open.tiktokapis.com/v2"
MIN_CHUNK = 5 * 1024 * 1024
CHUNK = 10 * 1024 * 1024


def access_token() -> str:
    r = requests.post(
        f"{API}/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": env("TIKTOK_CLIENT_KEY"),
            "client_secret": env("TIKTOK_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": env("TIKTOK_REFRESH_TOKEN"),
        },
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok login failed (re-run tools/get_tiktok_token.py): {data}")
    _maybe_rotate_refresh_token(data.get("refresh_token"))
    return data["access_token"]


def _maybe_rotate_refresh_token(new_token: str | None) -> None:
    """If TikTok hands out a new refresh token, save it back to the GitHub secret (needs GH_PAT)."""
    old = os.environ.get("TIKTOK_REFRESH_TOKEN", "")
    if not new_token or new_token == old:
        return
    repo, pat = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GH_PAT")
    if repo and pat:
        subprocess.run(
            ["gh", "secret", "set", "TIKTOK_REFRESH_TOKEN", "--repo", repo, "--body", new_token],
            env={**os.environ, "GH_TOKEN": pat}, check=False, capture_output=True,
        )
    else:
        print("Note: TikTok issued a new refresh token. Add a GH_PAT secret so it is saved automatically.")


def _post(path: str, token: str, body: dict) -> dict:
    r = requests.post(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        json=body, timeout=60,
    )
    data = r.json()
    err = data.get("error", {})
    if err.get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok {path} failed: {err.get('code')} - {err.get('message')}")
    return data.get("data", {})


def _chunk_plan(size: int) -> tuple[int, int]:
    # Files up to one chunk go in a single request; bigger files use 10 MB chunks and the
    # last chunk absorbs the remainder (TikTok allows 5-64 MB chunks, last one up to 128 MB).
    if size <= CHUNK:
        return size, 1
    return CHUNK, size // CHUNK


def _upload_file(upload_url: str, video: Path, chunk_size: int, count: int) -> None:
    size = video.stat().st_size
    with open(video, "rb") as f:
        for i in range(count):
            start = i * chunk_size
            end = size - 1 if i == count - 1 else start + chunk_size - 1  # last chunk takes the remainder
            f.seek(start)
            data = f.read(end - start + 1)
            for attempt in range(3):
                r = requests.put(
                    upload_url,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(data)),
                        "Content-Range": f"bytes {start}-{end}/{size}",
                    },
                    data=data, timeout=300,
                )
                if r.status_code in (200, 201, 206):
                    break
                if r.status_code < 500 or attempt == 2:
                    raise RuntimeError(f"TikTok upload chunk {i + 1}/{count} failed: {r.status_code} {r.text[:300]}")
                time.sleep(5)


def _wait(token: str, publish_id: str, done: set) -> str:
    status = "UNKNOWN"
    for _ in range(40):
        data = _post("/post/publish/status/fetch/", token, {"publish_id": publish_id})
        status = data.get("status", "UNKNOWN")
        if status in done:
            return status
        if status == "FAILED":
            raise RuntimeError(f"TikTok processing failed: {data.get('fail_reason')}")
        time.sleep(15)
    return status  # still processing; TikTok usually finishes on its own


def upload(video: Path, story: dict, cfg: dict) -> dict:
    tk = cfg["tiktok"]
    token = access_token()
    size = video.stat().st_size
    chunk_size, count = _chunk_plan(size)
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk_size, "total_chunk_count": count}

    if tk["mode"] == "direct":
        creator = _post("/post/publish/creator_info/query/", token, {})
        options = creator.get("privacy_level_options", [])
        privacy = next((p for p in tk["privacy_preference"] if p in options), None)
        if not privacy:
            raise RuntimeError(f"None of your privacy choices are allowed for this account: {options}")
        post_info = {
            "title": story["tiktok_caption"][:2200],
            "privacy_level": privacy,
            "disable_comment": bool(creator.get("comment_disabled", False)),
            "disable_duet": bool(creator.get("duet_disabled", False)),
            "disable_stitch": bool(creator.get("stitch_disabled", False)),
            "video_cover_timestamp_ms": 1000,
            "is_aigc": bool(tk["ai_label"]),
        }
        data = _post("/post/publish/video/init/", token, {"post_info": post_info, "source_info": source})
        done = {"PUBLISH_COMPLETE"}
    else:
        data = _post("/post/publish/inbox/video/init/", token, {"source_info": source})
        done = {"SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"}
        privacy = "draft in inbox"

    _upload_file(data["upload_url"], video, chunk_size, count)
    status = _wait(token, data["publish_id"], done)
    return {"publish_id": data["publish_id"], "status": status, "mode": tk["mode"], "privacy": privacy}
