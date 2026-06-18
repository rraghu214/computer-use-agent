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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import action
import driver
import perception
import planner
import recovery
from config import CALCULATOR_APP_NAME, CALCULATOR_EXPRESSION
from recorder import recorded_run, log_event

RUN_ID = "task1_calculator"

# Windows Calculator accepts the same characters as its on-screen buttons
# as direct keypresses; this maps the expression string to a press_key
# sequence. '=' or Enter both trigger evaluation -- Enter is used here.
_KEY_FOR_CHAR = {**{str(d): str(d) for d in range(10)}, ".": ".", "*": "*", "/": "/", "+": "+", "-": "-"}


def _expression_to_keys(expr: str) -> list[str]:
    return [_KEY_FOR_CHAR[ch] for ch in expr]


def run() -> dict:
    driver.ensure_daemon()
    subgoals = planner.decompose(
        f"Compute {CALCULATOR_EXPRESSION} in Calculator and read the result",
        known_subgoals=[f"Launch Calculator", f"Type {CALCULATOR_EXPRESSION}", "Press Enter", "Read the display"],
    )

    with recorded_run(RUN_ID) as run_dir:
        log_event(run_dir, "subgoals", subgoals=subgoals)

        pid, window_id = driver.launch_app(
            name=CALCULATOR_APP_NAME,
            fallback_argv=["calc.exe"],
        )
        log_event(run_dir, "launched", pid=pid, window_id=window_id)

        try:
            state = action.scan(pid, window_id)
        except driver.PreconditionError:
            state = recovery.recover_from_precondition(pid, window_id)
        log_event(run_dir, "scanned", element_count=state.get("element_count"))

        for key in _expression_to_keys(CALCULATOR_EXPRESSION):
            driver.press_key(pid, window_id, key)
        driver.press_key(pid, window_id, "Enter")
        log_event(run_dir, "keys_sent", expression=CALCULATOR_EXPRESSION)

        final_state = action.verify(
            pid, window_id,
            predicate=lambda s: perception.extract_direct(s.get("tree_markdown", ""), r"Display is (.+)") is not None,
        )
        result = perception.extract_direct(final_state.get("tree_markdown", ""), r"Display is (.+)")
        log_event(run_dir, "result", result=result)

        print(f"[task1] {CALCULATOR_EXPRESSION} = {result}")
        return {"task": RUN_ID, "result": result, "run_dir": str(run_dir)}


if __name__ == "__main__":
    run()
