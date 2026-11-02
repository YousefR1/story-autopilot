"""Builds the final 9:16 video with ffmpeg: footage + narration + optional music + captions."""
import json
import random
import subprocess
from pathlib import Path

from .config import MUSIC_DIR


def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:4])}...\n{p.stderr[-1500:]}")


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def make_segment(clip: Path, seconds: float, out: Path, cfg: dict) -> Path:
    v = cfg["video"]
    w, h, fps = v["width"], v["height"], v["fps"]
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},"
        f"eq=brightness=-0.06:saturation=0.9,format=yuv420p"
    )
    run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(clip), "-t", f"{seconds:.3f}",
        "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out),
    ])
    return out


MOTIONS = ["zoom_in", "pan_right", "zoom_out", "pan_left"]


def make_still_segment(image: Path, seconds: float, out: Path, cfg: dict, index: int) -> Path:
    """Slow 'Ken Burns' zoom or pan across a still image."""
    v = cfg["video"]
    w, h, fps = v["width"], v["height"], v["fps"]
    frames = max(2, round(seconds * fps))
    motion = MOTIONS[index % len(MOTIONS)]
    zmax = 1.14
    t = f"(on/{frames - 1})"  # 0 -> 1 across the segment
    if motion == "zoom_in":
        z, x, y = f"1+{zmax - 1}*{t}", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    elif motion == "zoom_out":
        z, x, y = f"{zmax}-{zmax - 1}*{t}", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    elif motion == "pan_right":
        z, x, y = f"{zmax}", f"(iw-iw/zoom)*{t}", "(ih-ih/zoom)/2"
    else:  # pan_left
        z, x, y = f"{zmax}", f"(iw-iw/zoom)*(1-{t})", "(ih-ih/zoom)/2"
    # Upscale 2x before zoompan so the motion is smooth instead of jittery.
    vf = (
        f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},"
        f"eq=brightness=-0.03:saturation=0.95,setsar=1,format=yuv420p"
    )
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image), "-vf", vf, "-frames:v", str(frames),
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(fps), str(out),
    ])
    return out


def render_video(clips: list[dict], durations: list[float], voice: Path, captions: Path,
                 out: Path, work: Path, cfg: dict) -> Path:
    segments = []
    for i, (c, d) in enumerate(zip(clips, durations)):
        seg = work / f"seg_{i:02d}.mp4"
        if c.get("kind") == "image":
            segments.append(make_still_segment(c["path"], d, seg, cfg, i))
        else:
            segments.append(make_segment(c["path"], d, seg, cfg))
    concat_list = work / "segments.txt"
    concat_list.write_text("".join(f"file '{s.name}'\n" for s in segments), encoding="utf-8")
    visuals = work / "visuals.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(visuals)])

    total = sum(durations)
    music = sorted(MUSIC_DIR.glob("*.mp3")) if MUSIC_DIR.exists() else []
    subs = str(captions).replace("\\", "/").replace(":", "\\:")
    cmd = ["ffmpeg", "-y", "-i", str(visuals), "-i", str(voice)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(random.choice(music))]
        vol = cfg["video"].get("music_volume", 0.08)
        audio = (f"[1:a]apad[voice];[2:a]volume={vol}[bg];"
                 f"[voice][bg]amix=inputs=2:duration=first:normalize=0,atrim=0:{total:.3f}[a]")
    else:
        audio = f"[1:a]apad,atrim=0:{total:.3f}[a]"
    cmd += [
        "-filter_complex", f"[0:v]subtitles='{subs}'[v];{audio}",
        "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(out),
    ]
    run(cmd)
    return out
