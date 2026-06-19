"""Task 1 -- Calculator: deterministic hotkeys, zero vision calls.

Satisfies the assignment's "at least one task completes with zero vision
calls" constraint, and is explicitly the task list's example #1 ("A
Calculator or simple-arithmetic task using deterministic hotkeys (Layer
2a)").

Cascade decision: the whole interaction is a fixed sequence of
press_key calls -- no judgment call is needed because the goal and the
keystrokes required to reach it are both known at write-time. Verifying
the result is Layer 1 (read the display straight out of the AX tree,
again zero LLM cost) rather than Layer 2b, because there's nothing to
judge -- only a value to read and compare.

Five-layer mapping for this task:
  Goal decomposition      -> a single known subgoal, no LLM (planner.decompose)
  Perception interpretation -> extract_direct() reads the display value
  Action sequencing        -> scan/act/verify around the fixed key sequence
  Error recovery            -> recovery.recover_from_precondition if the
                                 AX tree is empty after launch
  Vision fallback            -> never reached; this task proves the zero-
                                 vision floor of the cascade
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import action
import driver
import gateway
import perception
import planner
import recovery
from config import CALCULATOR_APP_NAME, CALCULATOR_EXPRESSION
from recorder import recorded_run, log_event

RUN_ID = "task1_calculator"

# Win11 Calculator is a packaged UWP app -- it ignores raw WM_KEYDOWN and
# WM_CHAR input (press_key and type_text use PostMessage which UWP's XAML
# input stack never sees).  The reliable path is clicking via element_index,
# which triggers UIA's InvokePattern directly on the button, bypassing the
# message pump entirely.  Still Layer 2a: the scan happens once, indices are
# read from the AX tree, every subsequent click is deterministic.

_BUTTON_TITLE_TO_CHAR = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "multiply by": "*", "divide by": "/", "plus": "+", "minus": "-",
    "decimal separator": ".", "equals": "=", "clear": "C", "backspace": "⌫",
}

_CHAR_TO_BUTTON_TITLE = {v: k for k, v in _BUTTON_TITLE_TO_CHAR.items()}


def _build_button_map(tree_markdown: str) -> dict[str, int]:
    """Parse element_index for each Calculator button by title (Layer 1 extraction)."""
    import re
    result = {}
    for m in re.finditer(r'\[(\d+)\] Button "([^"]+)"', tree_markdown):
        idx, title = int(m.group(1)), m.group(2).lower()
        result[title] = idx
    return result


def run() -> dict:
    driver.ensure_daemon()

    print(f"[task1] LAYER 1 — Goal decomposition: compute {CALCULATOR_EXPRESSION}")
    subgoals = planner.decompose(
        f"Compute {CALCULATOR_EXPRESSION} in Calculator and read the result",
        known_subgoals=["Launch Calculator", f"Type {CALCULATOR_EXPRESSION}", "Click Equals", "Read the display"],
    )

    with recorded_run(RUN_ID) as run_dir:
        log_event(run_dir, "subgoals", subgoals=subgoals)

        print(f"[task1] Action — launching Calculator")
        pid, window_id = driver.launch_app(
            name=CALCULATOR_APP_NAME,
            fallback_argv=["calc.exe"],
        )
        log_event(run_dir, "launched", pid=pid, window_id=window_id)
        print(f"[task1] Launch OK — pid={pid}, window_id={window_id}")
        driver.bring_to_front(pid, window_id)
        time.sleep(0.5)

        print(f"[task1] LAYER 2a — Perception/AX: scanning button layout")
        try:
            state = action.scan(pid, window_id)
        except driver.PreconditionError:
            print(f"[task1] Recovery — AX tree empty, retrying bring-to-front")
            state = recovery.recover_from_precondition(pid, window_id)
        log_event(run_dir, "scanned", element_count=state.get("element_count"))

        btn_map = _build_button_map(state.get("tree_markdown", ""))
        log_event(run_dir, "button_map", count=len(btn_map))
        print(f"[task1] LAYER 2a — found {len(btn_map)} buttons in AX tree (no LLM needed)")

        print(f"[task1] Action — entering expression via element_index clicks (UIA InvokePattern)")
        if "clear" in btn_map:
            driver.click(pid, window_id, element_index=btn_map["clear"])

        for ch in CALCULATOR_EXPRESSION:
            title = _CHAR_TO_BUTTON_TITLE.get(ch)
            if title and title in btn_map:
                driver.click(pid, window_id, element_index=btn_map[title])
            else:
                log_event(run_dir, "unmapped_char", ch=ch)

        if "equals" in btn_map:
            driver.click(pid, window_id, element_index=btn_map["equals"])
        log_event(run_dir, "expression_entered", expression=CALCULATOR_EXPRESSION)

        print(f"[task1] LAYER 1 — Perception/extract: reading display value from AX tree (zero LLM)")
        _DISPLAY_RE = r'Display is ([^"]+)'

        final_state = action.verify(
            pid, window_id,
            predicate=lambda s: perception.extract_direct(s.get("tree_markdown", ""), _DISPLAY_RE) is not None,
        )
        result = perception.extract_direct(final_state.get("tree_markdown", ""), _DISPLAY_RE)
        log_event(run_dir, "result", result=result)

        print(f"[task1] LAYER 1 — Vision fallback: NOT USED (result read directly from AX tree)")
        print(f"[task1] {CALCULATOR_EXPRESSION} = {result}")
        gateway.print_cost_summary(RUN_ID)
        return {"task": RUN_ID, "result": result, "run_dir": str(run_dir)}


if __name__ == "__main__":
    run()
