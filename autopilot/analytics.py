"""Collects views and subscribers over time for every channel and saves docs/analytics.json.

Run with:  python -m autopilot.analytics
Needs each channel's login token to include read access (reconnect it with docs/connect-youtube.html).
"""
import json
import os
from datetime import date, datetime, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .config import DOCS_DIR, ROOT, env, load_config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
OUT_FILE = DOCS_DIR / "analytics.json"


def _channel_configs() -> list[dict]:
    """Every channel the automation runs: config.yaml plus each file in agents/."""
    paths = [ROOT / "config.yaml"] + sorted((ROOT / "agents").glob("*.yaml"))
    return [load_config(p) for p in paths if p.exists()]


def _credentials(token_name: str) -> Credentials:
    return Credentials(
        token=None,
        refresh_token=env(token_name),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=env("YOUTUBE_CLIENT_ID"),
        client_secret=env("YOUTUBE_CLIENT_SECRET"),
        scopes=SCOPES,
    )


def _friendly(err: Exception) -> str:
    text = str(err)
    if "invalid_scope" in text or "insufficient" in text.lower() or "403" in text:
        return ("No read access yet. Reconnect this channel with docs/connect-youtube.html "
                "and replace its token secret.")
    if "accessNotConfigured" in text or "has not been used" in text:
        return "Turn on the 'YouTube Analytics API' in Google Cloud for this project."
    return text[:300]


def collect(cfg: dict) -> dict:
    agent = cfg["agent"]
    token_name = cfg.get("youtube", {}).get("token_secret", "YOUTUBE_REFRESH_TOKEN")
    entry = {"agent_id": agent["id"], "name": agent["name"]}
    if not os.environ.get(token_name, "").strip():
        entry["error"] = f"Secret {token_name} isn't available to the analytics job."
        return entry

    creds = _credentials(token_name)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)

    ch = yt.channels().list(part="snippet,statistics", mine=True).execute()["items"][0]
    stats, snip = ch["statistics"], ch["snippet"]
    start = snip["publishedAt"][:10]
    entry.update({
        "channel_id": ch["id"],
        "title": snip["title"],
        "url": f"https://www.youtube.com/channel/{ch['id']}",
        "created": start,
        "totals": {
            "views": int(stats.get("viewCount", 0)),
            "subscribers": int(stats.get("subscriberCount", 0)),
            "videos": int(stats.get("videoCount", 0)),
        },
    })

    rep = ya.reports().query(
        ids="channel==MINE", startDate=start, endDate=date.today().isoformat(),
        metrics="views,subscribersGained,subscribersLost", dimensions="day", sort="day",
    ).execute()

    days, views_total, subs_total = [], 0, 0
    for d, views, gained, lost in rep.get("rows", []):
        views_total += int(views)
        subs_total += int(gained) - int(lost)
        days.append({"d": d, "views": int(views), "views_total": views_total,
                     "subs_net": int(gained) - int(lost), "subs_total": subs_total})
    entry["daily"] = days
    return entry


def main() -> None:
    channels = []
    for cfg in _channel_configs():
        try:
            channels.append(collect(cfg))
        except Exception as e:  # one broken channel shouldn't hide the others
            channels.append({"agent_id": cfg["agent"]["id"], "name": cfg["agent"]["name"],
                             "error": _friendly(e)})
            print(f"{cfg['agent']['name']}: {e}")
    out = {"updated": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "channels": channels}
    OUT_FILE.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    for c in channels:
        print(f"{c['name']}: {'error: ' + c['error'] if 'error' in c else str(len(c['daily'])) + ' days'}")


if __name__ == "__main__":
    main()
