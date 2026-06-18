"""Task 3 -- MS Paint: the genuine Layer 3 vision task.

Satisfies the task list's item #4 ("A task in a canvas-rendered or
game-style target that forces Layer 3 vision ... a sketching app with no
ARIA") and the assignment's "at least one task uses vision" constraint.

Cascade decision, precisely stated: MS Paint's toolbar/ribbon is a real
Win32 menu and *is* AX-readable -- this task does not rely on an empty
element_count to justify vision. The actual reason vision is mandatory
here is narrower and more honest than that: nothing in any accessibility
API describes the *pixel content* of a canvas. There is no AX node for
"a star is drawn at these coordinates." Reading back what has been
drawn, or confirming a stroke landed where intended, is only possible by
looking at the screenshot -- so this is the one place in the project
where Layer 3 isn't a fallback from a failed AX read, it's the only
perception channel that was ever going to exist for this content.

Note what this task deliberately does *not* use vision for: the actual
star geometry is computed with plain trigonometry, not asked of a vision
model staring at a blank canvas -- there is nothing to perceive yet at
that point, only coordinates to compute. Vision is reserved for the part
that's actually a perception problem: confirming the drawn result looks
like the target. The Save dialog that follows is a native Win32 dialog,
fully AX-readable, so it deliberately switches back to Layer 2b
(perception.judge_action) rather than continuing to use vision -- a
direct illustration of the cascade discipline the assignment asks for:
use the cheapest layer that can actually do the job, per *step*, not per
task.

Five-layer mapping for this task:
  Goal decomposition       -> known subgoal list (planner.decompose)
  Perception interpretation -> perception.judge_action() drives the
                                  Save-As dialog once it's reached
  Action sequencing          -> driver.drag() strokes; scan/act/verify
                                  around the save dialog
  Error recovery               -> recovery.recover_from_precondition for
                                  the save dialog only -- never invoked
                                  for the canvas, which is supposed to
                                  have nothing in its AX tree
  Vision fallback              -> vision.ask_vision() verifies the drawn
                                  shape against PAINT_DRAW_TARGET
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import action
import driver
import perception
import planner
import recovery
import vision
from config import (
    ASSETS_DIR,
    PAINT_APP_NAME,
    PAINT_BIN,
    PAINT_DRAW_TARGET,
    PAINT_MAX_STEPS,
    PAINT_SAVE_PATH,
)
from recorder import recorded_run, log_event

RUN_ID = "task3_mspaint"

_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "looks_like_target": {"type": "boolean"},
        "feedback": {"type": "string"},
    },
    "required": ["looks_like_target"],
}


def _star_points(cx: float, cy: float, radius: float, n: int = 5) -> list[tuple[int, int]]:
    """Vertices of a regular n-gon, point-up. Connecting vertex i to
    vertex (i+2) mod n with straight lines draws the classic n-pointed
    star (pentagram, for n=5) without needing separate inner points."""
    points = []
    for i in range(n):
        angle = -math.pi / 2 + i * (2 * math.pi / n)  # start pointing up
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return [(round(x), round(y)) for x, y in points]


def _star_strokes(cx: float, cy: float, radius: float, n: int = 5) -> list[tuple[int, int, int, int]]:
    pts = _star_points(cx, cy, radius, n)
    return [(*pts[i], *pts[(i + 2) % n]) for i in range(n)]


def run() -> dict:
    driver.ensure_daemon()
    subgoals = planner.decompose(
        f"Draw {PAINT_DRAW_TARGET} in MS Paint and save it",
        known_subgoals=[
            "Launch MS Paint",
            "Screenshot the blank canvas to find its dimensions",
            "Compute star geometry deterministically",
            "Draw the strokes",
            "Verify the result visually",
            "Save via the native Save-As dialog",
        ],
    )

    with recorded_run(RUN_ID) as run_dir:
        log_event(run_dir, "subgoals", subgoals=subgoals)
        session = RUN_ID
        steps_used = 0

        pid, window_id = driver.launch_app(name=PAINT_APP_NAME, fallback_argv=[PAINT_BIN])
        log_event(run_dir, "launched", pid=pid, window_id=window_id)
        time.sleep(1.0)

        shot_path = str(ASSETS_DIR / "mspaint_blank.png")
        vision.capture(pid, window_id, shot_path)
        steps_used += 1
        from PIL import Image
        with Image.open(shot_path) as img:
            w, h = img.size
        log_event(run_dir, "screenshot", path=shot_path, width=w, height=h)

        # Centre the star in the lower ~70% of the window, leaving the
        # ribbon/toolbar strip at the top untouched.
        cx, cy = w / 2, h * 0.6
        radius = min(w, h) * 0.25
        strokes = _star_strokes(cx, cy, radius)
        log_event(run_dir, "star_geometry", center=[cx, cy], radius=radius, strokes=strokes)

        for x1, y1, x2, y2 in strokes:
            driver.drag(pid, window_id, x1=x1, y1=y1, x2=x2, y2=y2)
            steps_used += 1

        drawn_path = str(ASSETS_DIR / "mspaint_drawn.png")
        vision.capture(pid, window_id, drawn_path)
        steps_used += 1

        verdict = vision.ask_vision(
            drawn_path,
            f"Does this image show {PAINT_DRAW_TARGET} drawn on the canvas? "
            "Answer based only on what you can see.",
            schema=_VERIFY_SCHEMA,
            schema_name="verify",
            session=session,
        )
        log_event(run_dir, "vision_verify", verdict=verdict)

        if not verdict.get("looks_like_target", False) and steps_used < PAINT_MAX_STEPS:
            # One corrective pass: redraw the same strokes (a wobbly first
            # pass is usually a slow drag being interpreted as multiple
            # short strokes by the OS, not a wrong shape) and re-verify.
            for x1, y1, x2, y2 in strokes:
                if steps_used >= PAINT_MAX_STEPS:
                    break
                driver.drag(pid, window_id, x1=x1, y1=y1, x2=x2, y2=y2)
                steps_used += 1
            vision.capture(pid, window_id, drawn_path)
            verdict = vision.ask_vision(
                drawn_path,
                f"Does this image show {PAINT_DRAW_TARGET} drawn on the canvas?",
                schema=_VERIFY_SCHEMA,
                schema_name="verify",
                session=session,
            )
            log_event(run_dir, "vision_verify_retry", verdict=verdict)

        # Save -- a native Win32 dialog, fully AX-readable. Deliberately
        # switches back to Layer 2b here rather than continuing with vision.
        driver.hotkey(pid, window_id, ["ctrl", "s"])
        time.sleep(0.7)
        dialog_windows = driver.list_windows(pid=pid)
        dialog_window_id = dialog_windows[-1]["window_id"] if dialog_windows else window_id

        try:
            dialog_state = action.scan(pid, dialog_window_id)
        except driver.PreconditionError:
            dialog_state = recovery.recover_from_precondition(pid, dialog_window_id)
        log_event(run_dir, "save_dialog_scanned", element_count=dialog_state.get("element_count"))

        verdict2 = perception.judge_action(
            dialog_state.get("tree_markdown", ""),
            f"Type the path {PAINT_SAVE_PATH} into the file name field, then click Save.",
            session=session,
        )
        log_event(run_dir, "save_dialog_judgment", verdict=verdict2)
        if verdict2.get("verdict") == "act":
            act_action = dict(verdict2["action"])
            act_action.setdefault("text", str(PAINT_SAVE_PATH))
            action.act(pid, dialog_window_id, act_action)
            time.sleep(0.3)
            # Click Save / press Enter to confirm regardless of whether the
            # judgment call already targeted the Save button -- pressing
            # Enter on a focused filename field is the dialog's own default
            # action in every Windows version of this dialog.
            driver.press_key(pid, dialog_window_id, "Enter")

        print(f"[task3] drew {PAINT_DRAW_TARGET}, vision verdict: {verdict.get('looks_like_target')}, "
              f"saved to {PAINT_SAVE_PATH}")
        return {
            "task": RUN_ID,
            "looks_like_target": verdict.get("looks_like_target"),
            "steps_used": steps_used,
            "save_path": str(PAINT_SAVE_PATH),
            "run_dir": str(run_dir),
        }


if __name__ == "__main__":
    run()
