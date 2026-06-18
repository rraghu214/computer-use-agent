"""Layer 2 of 5: Perception interpretation.

Filters the AX tree markdown into something an LLM can act on. This is
the biggest cost-quality knob in the whole stack: pre-filter with the
driver's own `query` arg, summarise with a cheap model, or regex-extract
structured rows when no judgment is needed at all.

Two things live here, both genuinely "perception interpretation":

  extract_direct()  -- Layer 1 of the *cost cascade* (zero LLM calls).
                        Read a value straight out of tree_markdown. Try
                        this before anything else.

  judge_action()    -- Layer 2b of the cost cascade. Hands the (filtered)
                        tree_markdown plus the goal to a cheap text model
                        and gets back a structured verdict: either an
                        action to dispatch by element_index, or an
                        escalation reason (handed to vision.py).
"""
from __future__ import annotations

import json
import re
from typing import Optional

import gateway
from config import JUDGE_AGENT

# --------------------------------------------------------------------------
# Layer 1 (cost cascade): direct extraction, zero LLM calls
# --------------------------------------------------------------------------

def extract_direct(tree_markdown: str, label_pattern: str) -> Optional[str]:
    """Pulls a value out of tree_markdown by regex, no LLM involved.

    `label_pattern` is matched against each line; the first capture group
    of a match is returned. Use this for "what does the display say" /
    "what's in cell B3" style reads where the text is already in the tree.
    """
    for line in tree_markdown.splitlines():
        m = re.search(label_pattern, line)
        if m and m.groups():
            return m.group(1).strip()
    return None


def read_file(path: str) -> str:
    """The other Layer-1 source: a file's contents directly, zero LLM."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# --------------------------------------------------------------------------
# Filtering -- the "biggest knob"
# --------------------------------------------------------------------------

def trim_tree(tree_markdown: str, max_lines: int = 200) -> str:
    """Local trimming on top of the driver's own `query` pre-filter.
    Most AX trees for the targets in this project are small; this just
    guards against an unexpectedly large tree blowing up the judgment
    call's token cost."""
    lines = tree_markdown.splitlines()
    if len(lines) <= max_lines:
        return tree_markdown
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines truncated)"


# --------------------------------------------------------------------------
# Layer 2b (cost cascade): AX tree + cheap text LLM judgment
# --------------------------------------------------------------------------

_JUDGE_SYSTEM = (
    "You control a desktop app through its accessibility tree. You are "
    "given the current AX tree (as markdown, with actionable elements "
    "tagged [element_index N]) and a goal. Reply with strict JSON only, "
    "one of two shapes:\n"
    '  {"verdict": "act", "action": {"verb": "click|type_text|press_key|'
    'hotkey|set_value", "element_index": N, "text": "...", "key": "...", '
    '"keys": ["..."]}, "reason": "..."}\n'
    '  {"verdict": "escalate", "reason": "..."}\n'
    "Only include the action fields relevant to the chosen verb. Escalate "
    "if the tree has nothing relevant to the goal, or the goal is "
    "inherently visual."
)


def judge_action(
    tree_markdown: str,
    goal: str,
    *,
    agent: str = JUDGE_AGENT,
    session: Optional[str] = None,
) -> dict:
    """Returns a parsed verdict dict: {"verdict": "act", "action": {...}}
    or {"verdict": "escalate", "reason": "..."}.

    On any parsing failure, returns an escalate verdict rather than
    raising -- a malformed judgment should fall through to vision, not
    crash the task.
    """
    gateway.ensure_gateway()
    tree_markdown = trim_tree(tree_markdown)
    resp = gateway.LLM().chat(
        prompt=f"Goal: {goal}\n\nAX tree:\n{tree_markdown}",
        system=_JUDGE_SYSTEM,
        agent=agent,
        session=session,
        max_tokens=500,
    )
    text = resp.get("text", "")
    try:
        verdict = json.loads(text)
        if verdict.get("verdict") in ("act", "escalate"):
            return verdict
    except json.JSONDecodeError:
        pass
    return {"verdict": "escalate", "reason": f"unparseable judgment output: {text[:200]!r}"}
