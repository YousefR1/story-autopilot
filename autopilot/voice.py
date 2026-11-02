"""Narration (OpenAI text-to-speech) and word timings for captions (OpenAI transcription)."""
from pathlib import Path

from openai import OpenAI

from .config import env


def _client() -> OpenAI:
    return OpenAI(api_key=env("OPENAI_API_KEY"))


def narrate(cfg: dict, text: str, out_path: Path) -> Path:
    client = _client()
    with client.audio.speech.with_streaming_response.create(
        model=cfg["ai"]["tts_model"],
        voice=cfg["ai"]["voice"],
        input=text,
        instructions=cfg["ai"].get("voice_style", ""),
        response_format="mp3",
    ) as response:
        response.stream_to_file(out_path)
    return out_path


def word_timings(cfg: dict, audio_path: Path) -> list[dict]:
    """Returns [{"word": str, "start": float, "end": float}, ...]."""
    client = _client()
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model=cfg["ai"]["transcribe_model"],
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )
    words = getattr(result, "words", None) or []
    out = []
    for w in words:
        get = (lambda k: w[k]) if isinstance(w, dict) else (lambda k: getattr(w, k))
        out.append({"word": get("word").strip(), "start": float(get("start")), "end": float(get("end"))})
    if not out:
        raise RuntimeError("Transcription returned no word timings")
    return out
