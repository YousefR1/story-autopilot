"""Run history (what has been made) and dashboard status (what the dashboard shows)."""
import json
from datetime import datetime, timezone

from .config import DATA_DIR, DOCS_DIR

HISTORY_FILE = DATA_DIR / "history.json"
STATUS_FILE = DOCS_DIR / "status.json"
MAX_RUNS_SHOWN = 60


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


# ---------- history ----------

def load_history() -> dict:
    return _read(HISTORY_FILE, {"videos": [], "used_footage": []})


def save_history(history: dict) -> None:
    history["used_footage"] = history.get("used_footage", [])[-3000:]
    _write(HISTORY_FILE, history)


# ---------- dashboard status ----------

def load_status() -> dict:
    return _read(STATUS_FILE, {"updated": None, "agents": {}})


def agent_status(status: dict, cfg: dict) -> dict:
    a = cfg["agent"]
    entry = status["agents"].setdefault(a["id"], {
        "id": a["id"],
        "name": a["name"],
        "kind": "video",
        "platforms": [],
        "state": "idle",
        "consecutive_failures": 0,
        "totals": {"videos": 0, "youtube": 0, "tiktok": 0, "failures": 0},
        "runs": [],
    })
    entry["name"] = a["name"]
    entry["platforms"] = [p for p in ("youtube", "tiktok") if cfg[p]["enabled"]]
    entry["schedule"] = cfg.get("schedule_note", "")
    return entry


def record_run(status: dict, entry: dict, run: dict) -> None:
    entry["runs"].insert(0, run)
    entry["runs"] = entry["runs"][:MAX_RUNS_SHOWN]
    entry["last_run"] = run["finished"]
    status["updated"] = now_iso()
    _write(STATUS_FILE, status)


def save_status(status: dict) -> None:
    status["updated"] = now_iso()
    _write(STATUS_FILE, status)
