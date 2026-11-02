"""Uploads the finished video to YouTube (Shorts) with the YouTube Data API."""
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import env

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _service():
    creds = Credentials(
        token=None,
        refresh_token=env("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=env("YOUTUBE_CLIENT_ID"),
        client_secret=env("YOUTUBE_CLIENT_SECRET"),
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(video: Path, story: dict, credits: str, cfg: dict) -> dict:
    yt = cfg["youtube"]
    description = (
        f"{story['youtube_description']}\n\n"
        f"Narrated with an AI voice. {credits}\n\n#Shorts #stories"
    )
    body = {
        "snippet": {
            "title": story["youtube_title"][:100],
            "description": description[:4900],
            "tags": [t[:30] for t in story.get("tags", [])][:15],
            "categoryId": yt["category_id"],
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": yt["privacy"],
            "selfDeclaredMadeForKids": bool(yt["made_for_kids"]),
            "containsSyntheticMedia": bool(yt["ai_label"]),
        },
    }
    request = _service().videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    vid = response["id"]
    return {"id": vid, "url": f"https://youtube.com/shorts/{vid}"}
