"""Picks today's story and writes the script, titles and captions with Claude."""
import json
import re

import anthropic

from .config import env


def pick_genre(cfg: dict, history: dict) -> str:
    genres = cfg["stories"]["genres"]
    if not cfg["stories"].get("allow_true_stories", True):
        genres = [g for g in genres if "fiction" in g.lower() or "legend" in g.lower()] or genres
    last_used = {}
    for i, v in enumerate(history["videos"]):
        last_used[v.get("genre")] = i
    # least recently used first; never-used genres come first of all
    return sorted(genres, key=lambda g: last_used.get(g, -1))[0]


SYSTEM = """You write scripts for a faceless short-form story channel (YouTube Shorts and TikTok).
Every video is narrated by an AI voice over stock footage, with burned-in captions.
You choose the specific story yourself. Make each one feel fresh and specific, never generic.
Return ONLY valid JSON, no markdown fences."""


def build_prompt(cfg: dict, genre: str, history: dict) -> str:
    s = cfg["stories"]
    recent = [v["title"] for v in history["videos"][-80:]]
    true_rule = (
        "If the story is real, use only well-established, widely documented facts. "
        "Do not invent names, dates, quotes or numbers. If you are not sure of a detail, leave it out. "
        "If you cannot recall a real story with confidence, write labelled fiction instead."
        if s.get("allow_true_stories", True)
        else "Write original fiction only and make clear in the caption that it is fiction."
    )
    return f"""Channel: {cfg['channel']['name']}
Language: {cfg['channel']['language']}
Today's genre: {genre}
Tone: {s['tone']}
Length: about {s['target_words']} words of narration in total (strict range: {int(s['target_words']*0.85)}-{int(s['target_words']*1.15)}).
Never include: {', '.join(s['avoid'])}.
{true_rule}

Recently used titles (do NOT repeat these stories or close variants):
{json.dumps(recent, ensure_ascii=False)}

Structure:
- First sentence is a hook that makes people stop scrolling.
- Build tension, then a satisfying payoff or twist in the last 1-2 sentences.
- Split the narration into 6-10 scenes. Each scene is 1-2 sentences.
- For each scene give a stock-footage search phrase (2-4 plain English words, visual, no names
  of real people or brands, e.g. "foggy forest night", "old lighthouse storm").

Return this JSON:
{{
  "story_kind": "fiction" | "true" | "legend",
  "topic": "one-line summary of the specific story",
  "scenes": [{{"text": "narration", "search": "footage search phrase"}}],
  "youtube_title": "max 70 characters, curiosity-driven, no clickbait lies",
  "youtube_description": "2-3 sentences. Mention if it is fiction or legend.",
  "tags": ["8-12 lowercase tags"],
  "tiktok_caption": "1 short line + 4-6 hashtags, max 150 characters"
}}"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


def validate(story: dict, cfg: dict) -> None:
    scenes = story.get("scenes") or []
    if not 4 <= len(scenes) <= 14:
        raise ValueError(f"Script has {len(scenes)} scenes; expected 6-10")
    words = sum(len(s["text"].split()) for s in scenes)
    target = cfg["stories"]["target_words"]
    if not target * 0.6 <= words <= target * 1.6:
        raise ValueError(f"Script is {words} words; target is {target}")
    for key in ("youtube_title", "youtube_description", "tiktok_caption"):
        if not story.get(key):
            raise ValueError(f"Script is missing {key}")


def write_story(cfg: dict, history: dict) -> dict:
    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))
    genre = pick_genre(cfg, history)
    prompt = build_prompt(cfg, genre, history)
    last_error = None
    for _ in range(3):
        msg = client.messages.create(
            model=cfg["ai"]["writer_model"],
            max_tokens=2500,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            story = _parse_json(text)
            validate(story, cfg)
            story["genre"] = genre
            story["youtube_title"] = story["youtube_title"][:100]
            return story
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            last_error = e
            prompt += f"\n\nYour previous answer was rejected: {e}. Fix it and return only the JSON."
    raise RuntimeError(f"Could not get a valid script: {last_error}")
