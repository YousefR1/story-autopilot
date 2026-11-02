"""Timed, bold, centered captions (ASS subtitle file) and scene timing."""
import re
from pathlib import Path

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,{size},&H00FFFFFF,&H0000E5FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _clean(word: str) -> str:
    return re.sub(r"[{}\\]", "", word).upper()


def write_ass(words: list[dict], out: Path, cfg: dict, end_time: float) -> Path:
    v = cfg["video"]
    per = max(1, int(v.get("caption_words_per_line", 3)))
    groups = [words[i : i + per] for i in range(0, len(words), per)]
    lines = [ASS_HEADER.format(w=v["width"], h=v["height"], size=int(v["width"] * 0.085))]
    for gi, g in enumerate(groups):
        start = g[0]["start"]
        nxt = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else end_time
        end = min(max(g[-1]["end"], start + 0.3), nxt) if gi + 1 < len(groups) else end_time
        # highlight each word in yellow while it is spoken
        for wi, w in enumerate(g):
            w_start = w["start"] if wi else start
            w_end = g[wi + 1]["start"] if wi + 1 < len(g) else end
            if w_end <= w_start:
                continue
            parts = []
            for wj, other in enumerate(g):
                txt = _clean(other["word"])
                parts.append("{\\c&H00E5FF&}" + txt + "{\\c&HFFFFFF&}" if wj == wi else txt)
            lines.append(f"Dialogue: 0,{_ts(w_start)},{_ts(w_end)},Cap,,0,0,0,,{' '.join(parts)}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def scene_durations(scenes: list[dict], words: list[dict], total: float) -> list[float]:
    """Splits the narration timeline between scenes by their share of the words."""
    counts = [max(1, len(s["text"].split())) for s in scenes]
    script_total = sum(counts)
    n = len(words)
    bounds, acc = [], 0
    for c in counts[:-1]:
        acc += c
        idx = min(n - 1, round(acc / script_total * n))
        bounds.append(words[idx]["start"])
    edges = [0.0] + bounds + [total]
    durs = [max(0.8, edges[i + 1] - edges[i]) for i in range(len(scenes))]
    # keep the sum exactly equal to the total
    durs[-1] = max(0.8, total - sum(durs[:-1]))
    return durs
