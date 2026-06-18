"""Recording and replay.

Every submitted run must be recorded -- the trajectory directory is the
submission's evidence. This wraps start_recording/stop_recording as a
context manager so a task can't forget the stop_recording() in its
finally branch, and keeps a lightweight human-readable run log alongside
the trajectory for quick reference (the trajectory itself is cua-driver's
own (tool, args) pair format, not something this project reformats).
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import driver
from config import trajectory_dir


@contextmanager
def recorded_run(run_id: str) -> Iterator[Path]:
    """Usage:
        with recorded_run("task1_calculator") as run_dir:
            ...task logic...
    Guarantees stop_recording() runs even if the task raises.
    """
    run_dir = trajectory_dir(run_id)
    driver.start_recording(str(run_dir))
    log_path = run_dir / "run_log.jsonl"
    started_at = time.time()
    try:
        yield run_dir
    finally:
        driver.stop_recording()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "run_finished", "duration_s": round(time.time() - started_at, 2)}) + "\n")


def log_event(run_dir: Path, event: str, **fields) -> None:
    """Appends one line to this run's human-readable log -- separate from
    cua-driver's own trajectory format, just for quick eyeballing without
    needing the replay viewer."""
    log_path = run_dir / "run_log.jsonl"
    record = {"event": event, "ts": round(time.time(), 3), **fields}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
