"""Thin wrapper around the `cua-driver` CLI.

cua-driver gives perception and action; nothing here decomposes goals,
interprets perception, recovers from errors, or does vision -- those are
the five layers built on top (see planner.py, decision.py, action.py,
recovery.py, vision.py). This module only ever does what the guide's own
JSON tool surface documents, with no invented tools.

Corrections this wrapper bakes in, versus the obvious-looking API:
  - The AX tree field in get_window_state's response is `tree_markdown`,
    not `ax_tree`.
  - There is no standalone `screenshot` tool. Screenshots come from
    get_window_state(capture_mode="vision", screenshot_out_file=...).
  - launch_app's own examples only return `pid` -- window_id comes from a
    separate list_windows call filtered by that pid.
  - bring_to_front is a documented no-op on macOS/Linux but works on
    Windows via SetForegroundWindow.
  - click() addresses by element_index OR by raw (x, y) pixel coordinates
    (the vision-fallback case).
  - cua-driver shutdown is a real emergency-stop subcommand.

One genuine unknown, left unresolved on purpose rather than guessed: every
launch_app example in the guide uses either `bundle_id` (macOS) or a bare
`name` (the VS Code example) -- there is no Windows-specific schema shown.
launch_app() below tries the documented shape first and falls back to a
plain subprocess launch + list_apps/list_windows polling if that tool call
fails. Run `cua-driver describe launch_app` on the real machine to confirm
the exact Windows schema and simplify this if it turns out unnecessary.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from config import CUA_DRIVER_BIN, DAEMON_START_WAIT_S


class PreconditionError(RuntimeError):
    """Raised when cua-driver returns an empty AX tree or a blocked
    precondition. Mirrors the guard pattern from CUA_DRIVER_GUIDE.md
    section 8 exactly -- this is the single check that catches most of
    the "traps that look the same" the guide warns about."""


class DriverCallError(RuntimeError):
    """A cua-driver CLI invocation itself failed (non-zero exit, bad JSON)."""


# --------------------------------------------------------------------------
# Daemon lifecycle
# --------------------------------------------------------------------------

def ensure_daemon() -> None:
    """Start `cua-driver serve` if it is not already running. Idempotent.
    Exact shape from the guide's own example."""
    if subprocess.run([CUA_DRIVER_BIN, "status"], capture_output=True).returncode != 0:
        subprocess.Popen([CUA_DRIVER_BIN, "serve"])
        time.sleep(DAEMON_START_WAIT_S)


def shutdown_daemon() -> None:
    """Emergency stop: kills the daemon, the agent stops within a second.
    Documented recovery primitive -- wire this to a kill-switch if you
    add any kind of always-on control surface later."""
    subprocess.run([CUA_DRIVER_BIN, "shutdown"], capture_output=True)


# --------------------------------------------------------------------------
# Generic call plumbing
# --------------------------------------------------------------------------

def call(tool: str, args: Optional[dict[str, Any]] = None) -> dict:
    """`cua-driver call <tool> '<json args>'`, parsed back to a dict."""
    args = args or {}
    proc = subprocess.run(
        [CUA_DRIVER_BIN, "call", tool, json.dumps(args)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise DriverCallError(
            f"cua-driver call {tool} failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )
    if not proc.stdout.strip():
        return {"ok": True}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        # cua-driver v0.5+ returns plain-text confirmations for action tools
        # (press_key, click, type_text, hotkey, drag, scroll, set_value).
        # Treat any non-JSON stdout with exit 0 as a success acknowledgement.
        return {"ok": True, "text": proc.stdout.strip()}


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------

def list_apps() -> list[dict]:
    return call("list_apps", {}).get("apps", [])


def list_windows(pid: Optional[int] = None) -> list[dict]:
    windows = call("list_windows", {}).get("windows", [])
    if pid is not None:
        windows = [w for w in windows if w.get("pid") == pid]
    return windows


def find_window_for_pid(pid: int, retries: int = 8, delay_s: float = 0.5) -> Optional[int]:
    """launch_app only hands back a pid -- window_id needs its own
    list_windows lookup, retried briefly in case the window hasn't
    materialised yet (the same race the guide's macOS background-launch
    trap describes; harmless extra insurance on Windows too)."""
    for _ in range(retries):
        for w in list_windows(pid=pid):
            if "window_id" in w:
                return w["window_id"]
        time.sleep(delay_s)
    return None


def find_window_by_title(title_substr: str, retries: int = 10, delay_s: float = 0.5) -> Optional[tuple[int, int]]:
    """Search all windows for one whose title contains title_substr.
    Returns (pid, window_id) or None.

    Used as a fallback for Windows 11 packaged apps (Calculator, Paint,
    Notepad) where launch_app returns the stub launcher's pid -- the stub
    exits and the real app process has a completely different pid.
    """
    title_substr_lower = title_substr.lower()
    for _ in range(retries):
        for w in list_windows():
            if title_substr_lower in w.get("title", "").lower():
                wid = w.get("window_id")
                wpid = w.get("pid")
                if wid is not None and wpid is not None:
                    return wpid, wid
        time.sleep(delay_s)
    return None


def find_app_by_name(name_substr: str) -> Optional[dict]:
    name_substr = name_substr.lower()
    for app in list_apps():
        if name_substr in app.get("name", "").lower():
            return app
    return None


# --------------------------------------------------------------------------
# Launch / lifecycle
# --------------------------------------------------------------------------

def launch_app(
    *,
    name: Optional[str] = None,
    bundle_id: Optional[str] = None,
    path: Optional[str] = None,
    electron_debugging_port: Optional[int] = None,
    fallback_argv: Optional[list[str]] = None,
) -> tuple[int, Optional[int]]:
    """Returns (pid, window_id). window_id may be None if the window
    never showed up in list_windows within the retry budget -- callers
    should treat that as a precondition failure, not silently proceed.

    Tries the documented launch_app tool call first (bundle_id/name/path,
    optionally with electron_debugging_port for Electron apps). Falls back
    to a plain subprocess launch + list_apps/list_windows polling if the
    tool call itself errors -- see the module docstring for why this
    fallback exists.
    """
    args: dict[str, Any] = {}
    if bundle_id:
        args["bundle_id"] = bundle_id
    if name:
        args["name"] = name
    if path:
        args["path"] = path
    if electron_debugging_port:
        args["electron_debugging_port"] = electron_debugging_port

    pid: Optional[int] = None
    window_id: Optional[int] = None
    if args:
        try:
            result = call("launch_app", args)
            pid = result.get("pid")
        except DriverCallError:
            pid = None

    if pid is None:
        argv = fallback_argv or [path or name or bundle_id]
        proc = subprocess.Popen(argv)  # type: ignore[arg-type]
        pid = proc.pid
        time.sleep(1.5)

    # Give the app time to finish launching before polling.
    time.sleep(1.0)
    window_id = find_window_for_pid(pid)

    # On Windows 11, packaged apps (Calculator, Paint, Notepad) are launched
    # by a stub that immediately exits and re-routes to a separate host
    # process with a different pid.  find_window_for_pid(stub_pid) returns
    # None.  Fall back to a title search using the app name as a hint.
    if window_id is None and (name or bundle_id):
        title_hint = name or (bundle_id.split("!")[-1] if bundle_id else "")
        found = find_window_by_title(title_hint)
        if found:
            pid, window_id = found

    return pid, window_id


def launch_via_subprocess(
    argv: list[str],
    *,
    settle_s: float = 2.0,
    title_hint: Optional[str] = None,
) -> tuple[int, Optional[int]]:
    """Launch a process directly via subprocess, bypassing the launch_app
    tool call. Use this when the tool-level flags don't reach the process
    (e.g. electron_debugging_port is a no-op on Windows) and the full
    argv must be constructed by the caller.

    settle_s: seconds to wait after Popen before polling list_windows.
    title_hint: if the launched process exits immediately (e.g. Electron
        apps that delegate to an existing host process), fall back to
        searching for the NEW window matching this title -- windows already
        open before the launch are excluded, so a pre-existing window with
        the same title (e.g. another VS Code instance) is not returned.
    """
    # Snapshot existing windows so we can identify the newly-opened one.
    title_lower = (title_hint or "").lower()
    pre_existing: set[int] = set()
    if title_hint:
        pre_existing = {
            w["window_id"]
            for w in list_windows()
            if title_lower in w.get("title", "").lower() and "window_id" in w
        }

    proc = subprocess.Popen(argv)
    time.sleep(settle_s)

    window_id = find_window_for_pid(proc.pid)
    pid = proc.pid

    if window_id is None and title_hint:
        # Look for a window matching the title that wasn't there before launch.
        for _ in range(12):
            for w in list_windows():
                if title_lower in w.get("title", "").lower():
                    wid = w.get("window_id")
                    wpid = w.get("pid")
                    if wid is not None and wid not in pre_existing:
                        return wpid, wid
            time.sleep(0.5)

    return pid, window_id


def kill_app(pid: int) -> None:
    call("kill_app", {"pid": pid})


def bring_to_front(pid: int, window_id: Optional[int] = None) -> None:
    """Documented no-op on macOS/Linux; works on Windows via
    SetForegroundWindow. Cheap insurance -- never required to succeed."""
    try:
        args: dict[str, Any] = {"pid": pid}
        if window_id is not None:
            args["window_id"] = window_id
        call("bring_to_front", args)
    except DriverCallError:
        pass


# --------------------------------------------------------------------------
# Perception
# --------------------------------------------------------------------------

def get_window_state(
    pid: int,
    window_id: int,
    *,
    capture_mode: str = "ax",
    query: Optional[str] = None,
    screenshot_out_file: Optional[str] = None,
) -> dict:
    """capture_mode: "ax" | "som" | "vision".

    "ax" returns {element_count, tree_markdown, ...} and (re)builds the
    element_index cache for this (pid, window_id) -- call this once per
    turn before any element-indexed action (Invariant 1), and again after
    any state-changing action, since a new snapshot replaces the old
    index map entirely (Invariant 2).

    "vision" returns a screenshot only, written to screenshot_out_file.
    "som" returns both AX and a screenshot.
    """
    args: dict[str, Any] = {"pid": pid, "window_id": window_id, "capture_mode": capture_mode}
    if query:
        args["query"] = query
    if screenshot_out_file:
        args["screenshot_out_file"] = screenshot_out_file
    return call("get_window_state", args)


def require_nonempty_tree(state: dict) -> dict:
    """The single guard that catches most of the traps in section 8 of
    the guide. Raise immediately rather than letting a click silently
    fail with a cache-miss later."""
    if state.get("element_count", 0) == 0:
        raise PreconditionError(
            "cua-driver returned an empty AX tree. Check: (1) permissions "
            "granted, (2) app activated/in foreground, (3) Electron "
            "debugging port set if this is an Electron app, (4) this "
            "really is a canvas/game target that genuinely has no AX "
            "content -- in which case Layer 3 vision is correct, not a bug."
        )
    return state


def screenshot(pid: int, window_id: int, out_file: str) -> str:
    """Convenience wrapper: there is no standalone screenshot tool, this
    is exactly get_window_state(capture_mode="vision", ...)."""
    get_window_state(pid, window_id, capture_mode="vision", screenshot_out_file=out_file)
    return out_file


# --------------------------------------------------------------------------
# Action
# --------------------------------------------------------------------------

def click(
    pid: int,
    window_id: int,
    *,
    element_index: Optional[int] = None,
    x: Optional[int] = None,
    y: Optional[int] = None,
) -> dict:
    args: dict[str, Any] = {"pid": pid, "window_id": window_id}
    if element_index is not None:
        args["element_index"] = element_index
    else:
        args["x"], args["y"] = x, y
    return call("click", args)


def double_click(pid: int, window_id: int, *, x: int, y: int) -> dict:
    return call("double_click", {"pid": pid, "window_id": window_id, "x": x, "y": y})


def drag(pid: int, window_id: int, *, x1: int, y1: int, x2: int, y2: int) -> dict:
    return call(
        "drag",
        {"pid": pid, "window_id": window_id, "x1": x1, "y1": y1, "x2": x2, "y2": y2},
    )


def scroll(pid: int, window_id: int, *, dx: int = 0, dy: int = 0) -> dict:
    return call("scroll", {"pid": pid, "window_id": window_id, "dx": dx, "dy": dy})


def type_text(
    pid: int,
    window_id: int,
    text: str,
    *,
    element_index: Optional[int] = None,
    dispatch: str = "background",
) -> dict:
    args: dict[str, Any] = {"pid": pid, "window_id": window_id, "text": text}
    if element_index is not None:
        args["element_index"] = element_index
    if dispatch != "background":
        args["dispatch"] = dispatch
    return call("type_text", args)


def press_key(pid: int, window_id: int, key: str, *, dispatch: str = "background") -> dict:
    args: dict[str, Any] = {"pid": pid, "window_id": window_id, "key": key}
    if dispatch != "background":
        args["dispatch"] = dispatch
    return call("press_key", args)


def hotkey(pid: int, window_id: int, keys: list[str], *, dispatch: str = "background") -> dict:
    args: dict[str, Any] = {"pid": pid, "window_id": window_id, "keys": keys}
    if dispatch != "background":
        args["dispatch"] = dispatch
    return call("hotkey", args)


def set_value(pid: int, window_id: int, element_index: int, value: str) -> dict:
    return call(
        "set_value",
        {"pid": pid, "window_id": window_id, "element_index": element_index, "value": value},
    )


# --------------------------------------------------------------------------
# Electron / CDP
# --------------------------------------------------------------------------

def page(pid: int, action: str, **kwargs: Any) -> dict:
    """Full CDP surface for an app launched with electron_debugging_port
    (or webkit_inspector_port). Only used for Task 2 (VS Code) in this
    project -- deliberately never for Task 3, to keep the vision task
    free of any browser-automation tooling."""
    return call("page", {"pid": pid, "action": action, **kwargs})


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------

def start_recording(output_dir: str) -> dict:
    return call("start_recording", {"output_dir": output_dir})


def stop_recording() -> dict:
    return call("stop_recording", {})


def replay_trajectory(trajectory_dir: str) -> dict:
    return call("replay_trajectory", {"trajectory_dir": trajectory_dir})
