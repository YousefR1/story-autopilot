"""Collects public YouTube statistics for every posted video and its channel.

Writes docs/analytics.json, which the dashboard reads. Uses a YouTube Data API key
(GitHub secret YOUTUBE_API_KEY), so no logins and no AI credits are involved.

Usage: python -m autopilot.stats
"""
import json

import requests

from .config import DOCS_DIR, env
from .state import load_status, now_iso

API = "https://www.googleapis.com/youtube/v3"
OUT = DOCS_DIR / "analytics.json"


def _get(path: str, params: dict) -> dict:
    r = requests.get(f"{API}/{path}", params=params, timeout=30)
    data = r.json()
    if r.status_code != 200:
        msg = data.get("error", {}).get("message", r.text[:300])
        raise RuntimeError(f"YouTube API {path} failed: {msg}")
    return data


def _int(x) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def posted_videos(status: dict) -> dict:
    """{video_id: {"agent": agent_id, "posted": iso time}} for every video the agents posted."""
    out = {}
    for agent_id, agent in status.get("agents", {}).items():
        for run in agent.get("runs", []):
            yt = (run.get("posted") or {}).get("youtube")
            if yt and yt.get("id"):
                out[yt["id"]] = {"agent": agent_id, "posted": run.get("finished") or run.get("started")}
    return out


def collect() -> dict:
    key = env("YOUTUBE_API_KEY")
    status = load_status()
    wanted = posted_videos(status)
    videos, channel_of_agent = {}, {}

    ids = list(wanted)
    for i in range(0, len(ids), 50):
        data = _get("videos", {"part": "snippet,statistics", "id": ",".join(ids[i:i + 50]), "key": key})
        for item in data.get("items", []):
            s, sn = item.get("statistics", {}), item.get("snippet", {})
            vid = item["id"]
            agent = wanted[vid]["agent"]
            videos[vid] = {
                "agent": agent,
                "title": sn.get("title", ""),
                "channel_id": sn.get("channelId"),
                "posted": wanted[vid]["posted"],
                "views": _int(s.get("viewCount")),
                "likes": _int(s.get("likeCount")),
                "comments": _int(s.get("commentCount")),
            }
            if sn.get("channelId"):
                channel_of_agent[agent] = sn["channelId"]
    # Videos YouTube no longer returns (deleted or made private)
    for vid, meta in wanted.items():
        videos.setdefault(vid, {"agent": meta["agent"], "posted": meta["posted"], "missing": True,
                                "views": 0, "likes": 0, "comments": 0})

    channels = {}
    ch_ids = sorted(set(channel_of_agent.values()))
    if ch_ids:
        data = _get("channels", {"part": "snippet,statistics", "id": ",".join(ch_ids), "key": key})
        for item in data.get("items", []):
            s, sn = item.get("statistics", {}), item.get("snippet", {})
            channels[item["id"]] = {
                "title": sn.get("title", ""),
                "handle": sn.get("customUrl", ""),
                "subscribers": None if s.get("hiddenSubscriberCount") else _int(s.get("subscriberCount")),
                "views": _int(s.get("viewCount")),
                "videos": _int(s.get("videoCount")),
            }

    agents = {}
    for agent_id in status.get("agents", {}):
        mine = [v for v in videos.values() if v["agent"] == agent_id and not v.get("missing")]
        ch = channels.get(channel_of_agent.get(agent_id, ""), {})
        agents[agent_id] = {
            "channel": ch,
            "channel_id": channel_of_agent.get(agent_id),
            "videos": len(mine),
            "views": sum(v["views"] for v in mine),
            "likes": sum(v["likes"] for v in mine),
            "comments": sum(v["comments"] for v in mine),
            "avg_views": round(sum(v["views"] for v in mine) / len(mine), 1) if mine else 0,
            "top": max(mine, key=lambda v: v["views"])["title"] if mine else None,
        }

    previous = {}
    try:
        previous = json.loads(OUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    history = previous.get("history", [])
    history.append({
        "time": now_iso(),
        "agents": {a: {"views": v["views"], "subscribers": (v["channel"] or {}).get("subscribers")}
                   for a, v in agents.items()},
    })
    history = history[-240:]  # about 30 days at one snapshot every 3 hours

    return {"updated": now_iso(), "agents": agents, "videos": videos, "history": history}


def main() -> int:
    data = collect()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    total = sum(a["views"] for a in data["agents"].values())
    print(f"[ok] stats for {len(data['videos'])} videos, {total} total views")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
