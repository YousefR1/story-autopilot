"""Daily run: pick story -> script -> voice -> captions -> footage -> render -> check -> post -> log.

Usage:
  python -m autopilot.main            # normal run (posts)
  python -m autopilot.main --dry-run  # makes the video but does not post it
  python -m autopilot.main --force    # runs even if the agent paused itself
"""
import argparse
import shutil
import time
import traceback
from datetime import datetime, timezone

from . import captions, checks, footage, render, state, voice, writer
from .config import WORK_DIR, load_config
from .notify import notify


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    history = state.load_history()
    status = state.load_status()
    agent = state.agent_status(status, cfg)
    name = cfg["agent"]["name"]

    if not cfg["agent"]["enabled"]:
        agent["state"] = "paused"
        state.save_status(status)
        print("Agent is turned off in config.yaml (agent.enabled: false). Skipping.")
        return 0
    if agent.get("state") == "paused" and not args.force:
        print("Agent paused itself after repeated failures. Fix the issue, then run with --force.")
        state.save_status(status)
        return 0

    agent["state"] = "running"
    state.save_status(status)

    started = state.now_iso()
    t0 = time.time()
    run = {"started": started, "dry_run": args.dry_run, "steps": [], "result": "failed"}

    def step(label, fn):
        s = time.time()
        out = fn()
        run["steps"].append({"step": label, "seconds": round(time.time() - s, 1)})
        print(f"[ok] {label} ({time.time() - s:.1f}s)")
        return out

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True)

    try:
        story = step("write script", lambda: writer.write_story(cfg, history))
        run.update(title=story["youtube_title"], genre=story["genre"], kind=story.get("story_kind"),
                   topic=story.get("topic"))
        narration = " ".join(s["text"].strip() for s in story["scenes"])
        (WORK_DIR / "script.txt").write_text(narration, encoding="utf-8")

        voice_file = step("voiceover", lambda: voice.narrate(cfg, narration, WORK_DIR / "voice.mp3"))
        words = step("caption timing", lambda: voice.word_timings(cfg, voice_file))
        total = render.probe_duration(voice_file) + 0.8  # short tail after the last word
        durations = captions.scene_durations(story["scenes"], words, total)
        subs = captions.write_ass(words, WORK_DIR / "captions.ass", cfg, total)

        clips = step("stock footage", lambda: footage.get_scene_clips(story["scenes"], durations, history, WORK_DIR))
        authors = sorted({c["author"] for c in clips})
        credits = "Footage: Pexels (" + ", ".join(authors[:6]) + ")."

        final = WORK_DIR / "final.mp4"
        step("render", lambda: render.render_video(clips, durations, voice_file, subs, final, WORK_DIR, cfg))
        run["video"] = step("quality check", lambda: checks.check_video(final, cfg))

        posted, errors = {}, []
        if not args.dry_run:
            if cfg["youtube"]["enabled"]:
                try:
                    from . import youtube
                    posted["youtube"] = step("upload youtube", lambda: youtube.upload(final, story, credits, cfg))
                    agent["totals"]["youtube"] += 1
                except Exception as e:  # keep going so TikTok still gets the video
                    errors.append(f"YouTube: {e}")
            if cfg["tiktok"]["enabled"]:
                try:
                    from . import tiktok
                    posted["tiktok"] = step("upload tiktok", lambda: tiktok.upload(final, story, cfg))
                    agent["totals"]["tiktok"] += 1
                except Exception as e:
                    errors.append(f"TikTok: {e}")

        run["posted"] = posted
        if errors:
            run["errors"] = errors
        run["result"] = "dry run" if args.dry_run else ("partial" if errors and posted else
                                                        "failed" if errors else "posted")

        if run["result"] in ("posted", "partial", "dry run"):
            agent["totals"]["videos"] += 1
            history["videos"].append({
                "date": datetime.now(timezone.utc).date().isoformat(),
                "title": story["youtube_title"], "topic": story.get("topic"), "genre": story["genre"],
                "posted": posted, "dry_run": args.dry_run,
            })
            history["used_footage"] = history.get("used_footage", []) + [c["pexels_id"] for c in clips]
            state.save_history(history)

        if run["result"] == "failed":
            raise RuntimeError("; ".join(errors))
        agent["consecutive_failures"] = 0
        msg = f"✅ {name}: {run['result']} — {story['youtube_title']}"
        if "youtube" in posted:
            msg += f"\nYouTube: {posted['youtube']['url']}"
        if "tiktok" in posted:
            msg += ("\nTikTok: draft is in your inbox, tap to post" if posted["tiktok"]["mode"] == "inbox"
                    else f"\nTikTok: {posted['tiktok']['status']}")
        if errors:
            msg += "\n⚠️ " + "; ".join(errors)
        notify(msg)
        code = 0

    except Exception as e:
        traceback.print_exc()
        run["result"] = "failed"
        run["error"] = str(e)[:800]
        agent["totals"]["failures"] += 1
        agent["consecutive_failures"] = agent.get("consecutive_failures", 0) + 1
        notify(f"❌ {name} failed: {str(e)[:500]}")
        code = 1

    run["finished"] = state.now_iso()
    run["seconds"] = round(time.time() - t0, 1)
    limit = cfg["agent"].get("max_consecutive_failures", 3)
    if agent["consecutive_failures"] >= limit:
        agent["state"] = "paused"
        notify(f"⏸️ {name} paused itself after {limit} failed runs in a row.")
    else:
        agent["state"] = "idle"
    state.record_run(status, agent, run)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
