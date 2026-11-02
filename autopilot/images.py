"""AI-generated scene images (OpenAI Images API), one per scene."""
import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

from .config import env

SAFE_FALLBACK = "A dark, atmospheric, empty landscape at night under a moody sky, cinematic, no people"


def _prompt(scene: dict, cfg: dict) -> str:
    v = cfg["visuals"]
    subject = scene.get("image") or scene.get("search") or scene["text"]
    return (
        f"{subject}. {v['style']}. Vertical 9:16 composition with the main subject in the middle third. "
        "No text, letters, captions, logos, watermarks or signatures. "
        "Do not depict real, identifiable people."
    )


def _generate(client: OpenAI, prompt: str, out: Path, cfg: dict) -> Path:
    v = cfg["visuals"]
    result = client.images.generate(
        model=v["image_model"],
        prompt=prompt,
        size=v["image_size"],
        quality=v["image_quality"],
        output_format="jpeg",
        n=1,
    )
    data = result.data[0].b64_json if result.data else None
    if not data:
        raise RuntimeError("Image API returned no image data")
    out.write_bytes(base64.b64decode(data))
    return out


def _scene_image(client: OpenAI, i: int, scene: dict, work: Path, cfg: dict) -> Path:
    out = work / f"img_{i:02d}.jpg"
    try:
        return _generate(client, _prompt(scene, cfg), out, cfg)
    except Exception as e:
        # Usually a safety refusal for a dark scene: fall back to a neutral moody image.
        print(f"Scene {i + 1} image failed ({str(e)[:160]}); using a fallback image")
        return _generate(client, f"{SAFE_FALLBACK}. {cfg['visuals']['style']}. No text.", out, cfg)


def get_scene_images(scenes: list[dict], work: Path, cfg: dict) -> list[dict]:
    client = OpenAI(api_key=env("OPENAI_API_KEY"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(lambda a: _scene_image(client, a[0], a[1], work, cfg), enumerate(scenes)))
    return [{"path": p, "kind": "image"} for p in paths]
