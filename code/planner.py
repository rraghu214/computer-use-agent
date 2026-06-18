"""Layer 1 of 5: Goal decomposition.

Maps a natural-language goal to ordered app-level subgoals. Cost knob:
frontier vs. cheap model for the planner -- or, cheapest of all, a
pre-scripted subgoal list when the task is already well understood at
write-time.

All three tasks in this project use the free path: their subgoal lists
are known and fixed, so decompose() returns them straight back without
spending a call. The LLM path is implemented and real, not a stub -- it's
there for the case where a task's goal is supplied as free text at
runtime instead of being one of the three pre-scripted demos.
"""
from __future__ import annotations

import json
from typing import Optional

import gateway
from config import JUDGE_AGENT

_DECOMPOSE_SYSTEM = (
    "You split a desktop-automation goal into a short ordered list of "
    "concrete app-level subgoals. Reply with strict JSON only: "
    '{"subgoals": ["...", "..."]}. Keep each subgoal to one sentence. '
    "No more than 6 subgoals."
)


def decompose(goal: str, *, known_subgoals: Optional[list[str]] = None, session: Optional[str] = None) -> list[str]:
    """Returns an ordered list of subgoal strings.

    If `known_subgoals` is given (the case for all three tasks in this
    project), returns it unchanged -- zero LLM cost, the same "boring but
    cheap" philosophy as Layer 2a's hotkey sequences.

    Otherwise calls the gateway with a cheap text model to split `goal`
    into subgoals at runtime.
    """
    if known_subgoals is not None:
        return known_subgoals

    gateway.ensure_gateway()
    resp = gateway.LLM().chat(
        prompt=f"Goal: {goal}",
        system=_DECOMPOSE_SYSTEM,
        agent=JUDGE_AGENT,
        session=session,
        max_tokens=400,
    )
    text = resp.get("text", "{}")
    try:
        parsed = json.loads(text)
        subgoals = parsed.get("subgoals", [])
        if subgoals:
            return subgoals
    except (json.JSONDecodeError, AttributeError):
        pass
    # Degenerate fallback: treat the whole goal as one subgoal rather than
    # raising -- a planner failure shouldn't be fatal for a single-step task.
    return [goal]
