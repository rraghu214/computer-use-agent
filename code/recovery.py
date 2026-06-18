"""Layer 4 of 5: Error recovery.

Element gone after re-scan, permission denied, unexpected modal, app
crashed. Cost knob: how much state you carry across the failure.

The guide's section 8 ("traps that look the same") documents four
distinct causes that all surface identically as element_count: 0 or a
cache-miss on a click that should have worked:

  1. Permissions not granted               -> PreconditionError, no retry
  2. App launched but window not realised   -> activate, sleep, re-scan
  3. (Linux/Qt only -- not applicable here, project targets Windows)
  4. Cache miss from a UI reflow             -> just re-scan, no special case
  5. Electron app, opaque AXWebArea          -> needs electron_debugging_port
  6. Canvas/game target, no AX nodes at all  -> genuinely Layer 3, not a bug

This module gives a single recovery attempt for the "transient" causes
(2 and 4) and a clear, distinguishing error message for the rest, so a
task never just retries forever against a target that was never going
to have an AX tree in the first place.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional, TypeVar

import driver

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    *,
    retries: int = 3,
    delay_s: float = 0.5,
    retry_on: tuple[type[Exception], ...] = (driver.DriverCallError,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
) -> T:
    """Generic retry helper for the transient-error case (cache miss from
    a UI reflow, a flaky daemon call). Not used for PreconditionError --
    see recover_from_precondition() for that, since an empty tree needs a
    different response than "try again"."""
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return fn()
        except retry_on as e:
            last_exc = e
            if on_retry:
                on_retry(attempt, e)
            if attempt < retries - 1:
                time.sleep(delay_s)
    assert last_exc is not None
    raise last_exc


def recover_from_precondition(
    pid: int,
    window_id: int,
    *,
    is_vision_only_target: bool = False,
    query: Optional[str] = None,
) -> dict:
    """Called when scan() raises PreconditionError. Attempts the one
    documented recovery step (bring window to front, short sleep,
    re-scan) and re-raises with a clearer message if that doesn't help.

    If `is_vision_only_target` is True, this is a Task 3-style target
    (canvas/game) where an empty tree is the *expected*, correct outcome
    -- recovery should not retry at all, it should hand straight back to
    the caller so it can fall through to vision.py.
    """
    if is_vision_only_target:
        raise driver.PreconditionError(
            "Empty AX tree on a canvas/game target -- this is expected, not "
            "a fault. Fall through to vision.py rather than retrying."
        )

    driver.bring_to_front(pid)
    time.sleep(0.5)
    state = driver.get_window_state(pid, window_id, capture_mode="ax", query=query)
    if state.get("element_count", 0) == 0:
        raise driver.PreconditionError(
            "AX tree still empty after bring_to_front + re-scan. Check "
            "permissions and that the target app is actually an Electron "
            "app needing electron_debugging_port."
        )
    return state


def safe_kill(pid: Optional[int]) -> None:
    """Best-effort app teardown for error/finally paths -- never raises."""
    if pid is None:
        return
    try:
        driver.kill_app(pid)
    except Exception:
        pass
