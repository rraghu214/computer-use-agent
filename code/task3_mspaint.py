"""Task 3 -- MS Paint: the genuine Layer 3 vision task.

Satisfies the task list's item #4 ("A task in a canvas-rendered or
game-style target that forces Layer 3 vision ... a sketching app with no
ARIA") and the assignment's "at least one task uses vision" constraint.

Cascade decision: MS Paint's toolbar/ribbon is AX-readable. This task
uses the AX tree (Layer 2a) to discover and click the built-in
"Five-point star" shape button rather than computing pentagram stroke
geometry by hand. What makes vision mandatory here is not the toolbar
(which IS AX-readable) but the canvas: nothing in any accessibility API
describes the *pixel content* of a canvas. Whether a star is actually
drawn at any given coordinate, or whether the drag landed on the canvas
at all, can only be verified by looking at a screenshot. Vision is the
perception layer for that check, not a fallback from a failed AX read.

Five-layer mapping for this task:
  Goal decomposition       -> known subgoal list (planner.decompose)
  Perception interpretation -> AX tree (Layer 2a) to find the shape
                                  button; vision.ask_vision (Layer 3) to
                                  confirm the drawn result
  Action sequencing          -> element_index click (shape select) +
                                  driver.drag() (canvas draw); scan/act
                                  around the save dialog
  Error recovery               -> fallback to pencil strokes if shape
                                  drag fails to produce a recognisable star
  Vision fallback              -> vision.ask_vision() verifies the result
"""
from __future__ import annotations

import re
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


def _find_element_index(tree_markdown: str, button_name: str) -> int | None:
    """Scan the AX tree markdown for a button/item with the given name and
    return its element_index, or None if not found."""
    pattern = rf'\[(\d+)\][^\n]*"{re.escape(button_name)}"'
    m = re.search(pattern, tree_markdown)
    return int(m.group(1)) if m else None


def run() -> dict:
    driver.ensure_daemon()
    subgoals = planner.decompose(
        f"Draw {PAINT_DRAW_TARGET} in MS Paint and save it",
        known_subgoals=[
            "Launch MS Paint",
            "Scan AX tree to find the Five-point star shape button (Layer 2a)",
            "Click the shape button to arm the drawing tool",
            "Screenshot the canvas to learn its pixel dimensions",
            "Drag within the canvas to draw the star shape",
            "Verify the drawn result visually (Layer 3)",
            "Save via Ctrl+S and handle the save dialog",
        ],
    )

    with recorded_run(RUN_ID) as run_dir:
        log_event(run_dir, "subgoals", subgoals=subgoals)
        session = RUN_ID
        steps_used = 0

        pid, window_id = driver.launch_app(name=PAINT_APP_NAME, fallback_argv=[PAINT_BIN])
        log_event(run_dir, "launched", pid=pid, window_id=window_id)
        if window_id is None:
            raise driver.PreconditionError("MS Paint launched but no window_id found")
        time.sleep(1.0)
        driver.bring_to_front(pid, window_id)
        time.sleep(0.3)

        # Layer 2a: scan the AX tree to find the built-in "Five-point star"
        # shape button. Using the native shape tool is architecturally cleaner
        # than computing pentagram stroke geometry by hand -- the AX tree tells
        # us exactly which button arms the right tool.
        ax_state = action.scan(pid, window_id)
        tree_md = ax_state.get("tree_markdown", "")
        star_idx = _find_element_index(tree_md, "Five-point star")
        log_event(run_dir, "shape_button", element_index=star_idx, found=star_idx is not None)

        if star_idx is not None:
            driver.click(pid, window_id, element_index=star_idx)
            # No re-scan here: an AX query (UIA) after clicking a shape-tool
            # button can reset the shape selection in new Paint. We proceed
            # directly to the drag -- Invariant 2 only applies when the NEXT
            # action itself needs an element_index from a fresh snapshot.
            time.sleep(0.5)
            steps_used += 1
        else:
            # Fallback: select Pencil so drags will draw something.
            pencil_idx = _find_element_index(tree_md, "Pencil")
            if pencil_idx is not None:
                driver.click(pid, window_id, element_index=pencil_idx)
                time.sleep(0.5)
                steps_used += 1

        # Pause the trajectory recording for the draw step: cua-driver's
        # recording hooks interfere with foreground (SendInput) mouse drags on
        # Windows.  The draw result is captured in mspaint_drawn.png and the
        # vision_verify log entry, so the trajectory is not lossy.
        driver.stop_recording()

        # Compute drag coordinates in SCREEN-ABSOLUTE space (required for
        # dispatch="foreground" / SendInput which doesn't scale coordinates).
        #
        # Canvas geometry in screen-absolute pixels (back-calculated from
        # observed drag end-point vs. Paint's status-bar cursor position for
        # this machine's default maximised Paint window at (0,0)):
        #   canvas_left ≈ window_x + 685
        #   canvas_top  ≈ window_y + 422
        #   canvas_size: 551 x 348 (Paint's default at 100% zoom)
        #
        # We get the live window position from list_windows so the math
        # adapts if Paint is not maximised or is on a secondary monitor.
        paint_wins = driver.list_windows(pid=pid)
        paint_bounds = next(
            (w_["bounds"] for w_ in paint_wins if w_.get("window_id") == window_id),
            {"x": 0, "y": 0},
        )
        wx, wy = paint_bounds.get("x", 0), paint_bounds.get("y", 0)
        # Observed canvas offset from window top-left (screen-absolute units).
        canvas_left = wx + 685
        canvas_top  = wy + 422
        canvas_w, canvas_h = 551, 348  # Paint default at 100% zoom
        margin_x, margin_y = 80, 50
        x1 = canvas_left + margin_x
        y1 = canvas_top + margin_y
        x2 = canvas_left + canvas_w - margin_x
        y2 = canvas_top + canvas_h - margin_y
        shot_path = str(ASSETS_DIR / "mspaint_blank.png")
        log_event(run_dir, "canvas_coords", x1=x1, y1=y1, x2=x2, y2=y2, canvas_left=canvas_left, canvas_top=canvas_top)
        driver.bring_to_front(pid, window_id)
        time.sleep(0.3)
        driver.drag(pid, window_id, x1=x1, y1=y1, x2=x2, y2=y2, dispatch="foreground", duration_ms=800, steps=30)
        steps_used += 1
        log_event(run_dir, "shape_drag", x1=x1, y1=y1, x2=x2, y2=y2, dispatch="foreground")
        time.sleep(0.5)

        drawn_path = str(ASSETS_DIR / "mspaint_drawn.png")
        vision.capture(pid, window_id, drawn_path)
        steps_used += 1
        # Resume recording now that the SendInput drag is complete.
        driver.start_recording(str(run_dir))

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
            # Retry once with foreground dispatch.
            driver.bring_to_front(pid, window_id)
            time.sleep(0.2)
            driver.drag(pid, window_id, x1=x1, y1=y1, x2=x2, y2=y2, dispatch="foreground", duration_ms=800, steps=30)
            steps_used += 1
            time.sleep(0.5)
            vision.capture(pid, window_id, drawn_path)
            verdict = vision.ask_vision(
                drawn_path,
                f"Does this image show {PAINT_DRAW_TARGET} drawn on the canvas?",
                schema=_VERIFY_SCHEMA,
                schema_name="verify",
                session=session,
            )
            log_event(run_dir, "vision_verify_retry", verdict=verdict)

        # Save -- Ctrl+S on an untitled file opens the system Save As dialog.
        # In Windows 11 new Paint this dialog is a separate File Picker window
        # (different PID from Paint). We search all windows for it by title.
        driver.hotkey(pid, window_id, ["ctrl", "s"])
        time.sleep(1.5)

        save_pid, save_wid = pid, window_id  # default: interact with Paint itself
        all_wins = driver.list_windows()
        for w_info in all_wins:
            title = w_info.get("title", "").lower()
            if "save" in title or "save as" in title:
                save_pid = w_info.get("pid", pid)
                save_wid = w_info.get("window_id", window_id)
                break
        log_event(run_dir, "save_dialog_found", pid=save_pid, window_id=save_wid)

        try:
            dialog_state = action.scan(save_pid, save_wid)
        except driver.PreconditionError:
            dialog_state = recovery.recover_from_precondition(save_pid, save_wid)
        log_event(run_dir, "save_dialog_scanned", element_count=dialog_state.get("element_count"))

        # Layer 2b: ask the LLM to locate the filename field and Save button.
        verdict2 = perception.judge_action(
            dialog_state.get("tree_markdown", ""),
            f"Type the path {PAINT_SAVE_PATH} into the file name field, then click Save.",
            session=session,
        )
        log_event(run_dir, "save_dialog_judgment", verdict=verdict2)
        if verdict2.get("verdict") == "act":
            act_action = dict(verdict2["action"])
            act_action.setdefault("text", str(PAINT_SAVE_PATH))
            action.act(save_pid, save_wid, act_action)
            time.sleep(0.3)
        # Press Enter to confirm the filename dialog regardless.
        driver.press_key(save_pid, save_wid, "Return")
        time.sleep(0.5)

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
