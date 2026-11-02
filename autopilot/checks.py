"""Quality checks the finished video must pass before anything is posted."""
import json
import subprocess
from pathlib import Path


def check_video(path: Path, cfg: dict) -> dict:
    v = cfg["video"]
    if not path.exists() or path.stat().st_size < 200_000:
        raise RuntimeError("Video file is missing or too small")
    info = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout)
    streams = info.get("streams", [])
    video = next((s for s in streams if s["codec_type"] == "video"), None)
    audio = next((s for s in streams if s["codec_type"] == "audio"), None)
    duration = float(info["format"]["duration"])
    problems = []
    if not video:
        problems.append("no video stream")
    elif (int(video["width"]), int(video["height"])) != (v["width"], v["height"]):
        problems.append(f"wrong size {video['width']}x{video['height']}")
    if not audio:
        problems.append("no audio stream")
    if not v["min_seconds"] <= duration <= v["max_seconds"]:
        problems.append(f"duration {duration:.1f}s outside {v['min_seconds']}-{v['max_seconds']}s")
    # silence check: mean volume should not be near silent
    vol = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    mean = next((float(l.split(":")[1].split()[0]) for l in vol.splitlines() if "mean_volume" in l), -99.0)
    if mean < -45:
        problems.append(f"audio is nearly silent ({mean} dB)")
    if problems:
        raise RuntimeError("Quality check failed: " + "; ".join(problems))
    return {"duration": round(duration, 1), "size_mb": round(path.stat().st_size / 1e6, 1), "mean_db": mean}
