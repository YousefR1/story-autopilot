"""Optional alerts to a Discord channel (set the DISCORD_WEBHOOK_URL secret to turn on)."""
import os

import requests


def notify(text: str) -> None:
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        requests.post(url, json={"content": text[:1900]}, timeout=15)
    except requests.RequestException:
        pass
