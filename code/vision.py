"""Layer 5 of 5: Vision fallback.

Captures screenshot, draws set-of-marks, calls V9's /v1/vision endpoint,
parses verdict. Cost knob: trigger threshold for escalation -- vision is
roughly 10x the per-turn cost of Layer 2b, so this should only ever be
reached when Layer 2b genuinely escalates, never as a first resort.

Two perceptual aids are supported, matching the guide's own description
("draws numbered marks over UI regions for a vision model to pick from
... or click by (x, y)"):

  draw_marks()   -- numbered boxes over known UI *regions* to choose
                    between (useful when there's a discrete menu of
                    targets to click).
  (no marks)     -- for a blank canvas with nothing to box, the vision
                    call is asked to return raw pixel coordinates
                    directly. Task 3 (mspaint) uses this path: there is
                    nothing on a blank canvas to number.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Optional

import gateway
import driver
from config import JUDGE_AGENT

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


def capture(pid: int, window_id: int, out_file: str) -> str:
    """Screenshot via get_window_state(capture_mode="vision", ...) --
    there is no standalone screenshot tool. See driver.screenshot()."""
    return driver.screenshot(pid, window_id, out_file)


def draw_marks(image_path: str, marks: list[dict[str, Any]], out_path: Optional[str] = None) -> str:
    """Draws numbered boxes over `marks` (each {"index": int, "box":
    [x1,y1,x2,y2]}) for a vision model to pick from. Only meaningful when
    there's a discrete set of regions to choose between -- skip this
    entirely for a blank canvas (Task 3 does)."""
    if not _PIL_AVAILABLE:
        raise RuntimeError("Pillow not installed -- pip install pillow")
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    for mark in marks:
        x1, y1, x2, y2 = mark["box"]
        draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=2)
        draw.text((x1 + 2, max(0, y1 - 14)), str(mark["index"]), fill=(255, 0, 0))
    out_path = out_path or str(Path(image_path).with_suffix(".marked.png"))
    img.save(out_path)
    return out_path


def to_data_url(image_path: str) -> str:
    data = Path(image_path).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


def ask_vision(
    image_path: str,
    prompt: str,
    *,
    system: Optional[str] = None,
    schema: Optional[dict[str, Any]] = None,
    schema_name: str = "out",
    agent: str = JUDGE_AGENT,
    session: Optional[str] = None,
) -> dict:
    """Calls the gateway's /v1/vision shim with the image at `image_path`.
    Returns the parsed schema object if `schema` was given, else the raw
    response dict (use result["text"])."""
    resp = gateway.vision(
        to_data_url(image_path),
        prompt,
        system=system,
        schema=schema,
        schema_name=schema_name,
        agent=agent,
        session=session,
    )
    if schema and resp.get("parsed") is not None:
        return resp["parsed"]
    return resp
