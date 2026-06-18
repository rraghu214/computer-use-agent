"""Layer 3 of 5: Action sequencing.

Translates subgoals into the scan-act-verify loop, respecting the
re-scan invariant. Cost knob: how aggressively you re-scan vs. cache.

Two invariants this module exists to enforce (straight from the guide):

  Invariant 1. Call get_window_state once per turn per window before any
  element-indexed action -- that call builds the element_index cache.

  Invariant 2. Every new get_window_state snapshot replaces the previous
  index map. An element_index from snapshot N is a turn-scoped token;
  re-scan after every state-changing action, never reuse an old index.

scan() and act() are kept as separate calls (not fused) specifically so
callers cannot accidentally reuse a stale index across turns -- act()
takes the action dict, not the scan result, so there's nothing left over
to misuse.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

import driver


def scan(pid: int, window_id: int, *, query: Optional[str] = None) -> dict:
    """Invariant 1: always call this before any element-indexed action.
    Raises PreconditionError (via require_nonempty_tree) if the AX tree
    comes back empty -- callers should let that propagate to recovery.py
    rather than catching it here."""
    state = driver.get_window_state(pid, window_id, capture_mode="ax", query=query)
    return driver.require_nonempty_tree(state)


def act(pid: int, window_id: int, action: dict[str, Any]) -> dict:
    """Dispatches a structured action dict to the matching driver call.
    Shared by both Layer 2a (hand-written fixed actions) and Layer 2b
    (LLM-judged actions) -- same dispatcher, different source of the
    action dict."""
    verb = action["verb"]
    if verb == "click":
        return driver.click(
            pid, window_id,
            element_index=action.get("element_index"),
            x=action.get("x"), y=action.get("y"),
        )
    if verb == "type_text":
        return driver.type_text(pid, window_id, action["text"], element_index=action.get("element_index"))
    if verb == "press_key":
        return driver.press_key(pid, window_id, action["key"])
    if verb == "hotkey":
        return driver.hotkey(pid, window_id, action["keys"])
    if verb == "set_value":
        return driver.set_value(pid, window_id, action["element_index"], action["value"])
    if verb == "double_click":
        return driver.double_click(pid, window_id, x=action["x"], y=action["y"])
    if verb == "drag":
        return driver.drag(pid, window_id, x1=action["x1"], y1=action["y1"], x2=action["x2"], y2=action["y2"])
    raise ValueError(f"unknown action verb: {verb!r}")


def verify(
    pid: int,
    window_id: int,
    predicate: Callable[[dict], bool],
    *,
    query: Optional[str] = None,
    retries: int = 3,
    delay_s: float = 0.4,
) -> dict:
    """Re-scans (Invariant 2: a fresh snapshot, never the pre-action one)
    and checks `predicate` against it, retrying briefly. This is the
    pattern the guide calls the most important one in the loop: a click
    returning success does not mean the action achieved its intent."""
    last_state: dict = {}
    for attempt in range(retries):
        last_state = scan(pid, window_id, query=query)
        if predicate(last_state):
            return last_state
        if attempt < retries - 1:
            time.sleep(delay_s)
    return last_state  # caller decides whether a failed predicate is fatal


def scan_act_verify(
    pid: int,
    window_id: int,
    action: dict[str, Any],
    predicate: Callable[[dict], bool],
    *,
    scan_query: Optional[str] = None,
    verify_query: Optional[str] = None,
) -> dict:
    """One full turn: scan, act, verify. Convenience wrapper for the
    common case; tasks that need finer control call scan/act/verify
    directly instead."""
    scan(pid, window_id, query=scan_query)
    act(pid, window_id, action)
    return verify(pid, window_id, predicate, query=verify_query)
