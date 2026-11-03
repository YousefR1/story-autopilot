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


DEFAULT_STRUCTURE = [
    "First sentence is a hook that makes people stop scrolling.",
    "Build tension, then a satisfying payoff or twist in the last 1-2 sentences.",
]


def system_prompt(cfg: dict) -> str:
    s = cfg["stories"]
    channel_type = s.get("channel_type", "faceless short-form story channel")
    item = s.get("item", "story")
    return f"""You write scripts for a {channel_type} (YouTube Shorts and TikTok).
Every video is narrated by an AI voice over AI-generated pictures, with burned-in captions.
You choose the specific {item} yourself. Make each one feel fresh and specific, never generic.
Return ONLY valid JSON, no markdown fences."""


def build_prompt(cfg: dict, genre: str, history: dict) -> str:
    s = cfg["stories"]
    item = s.get("item", "story")
    recent = [v["title"] for v in history["videos"][-80:]]
    if s.get("accuracy_rule"):
        true_rule = s["accuracy_rule"]
    elif s.get("allow_true_stories", True):
        true_rule = (
            "If the story is real, use only well-established, widely documented facts. "
            "Do not invent names, dates, quotes or numbers. If you are not sure of a detail, leave it out. "
            "If you cannot recall a real story with confidence, write labelled fiction instead."
        )
    else:
        true_rule = "Write original fiction only and make clear in the caption that it is fiction."
    structure = "\n".join(f"- {line}" for line in s.get("structure", DEFAULT_STRUCTURE))
    scenes = s.get("scenes", "5-6")
    return f"""Channel: {cfg['channel']['name']}
Language: {cfg['channel']['language']}
Today's theme: {genre}
Tone: {s['tone']}
Length: about {s['target_words']} words of narration in total (strict range: {int(s['target_words']*0.85)}-{int(s['target_words']*1.15)}).
Never include: {', '.join(s['avoid'])}.
{true_rule}

Recently used titles (do NOT repeat these {item} topics or close variants):
{json.dumps(recent, ensure_ascii=False)}

Structure:
{structure}
- Split the narration into {scenes} scenes. Each scene is 1-3 sentences.
- For each scene give:
  - "image": one vivid sentence describing a single picture for that moment (setting, light, mood,
    one clear focal subject). No real people's names or likenesses, no brands, no gore, no text in the image.
  - "search": a 2-4 word stock-footage phrase (e.g. "foggy forest night").
- Keep the main character's look consistent across "image" descriptions (repeat key details).

Return this JSON:
{{
  "story_kind": "fiction" | "true" | "legend" | "fact",
  "topic": "one-line summary of the specific {item}",
  "scenes": [{{"text": "narration", "image": "picture description", "search": "footage search phrase"}}],
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
        raise ValueError(f"Script has {len(scenes)} scenes; expected {cfg['stories'].get('scenes', '5-6')}")
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
            system=system_prompt(cfg),
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
