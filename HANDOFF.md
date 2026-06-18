# HANDOFF.md

For picking this project up in Claude Code (or any agent working from
this repo in VS Code). Read this before changing anything -- it says
what's been verified, what hasn't, and where the real risk in this
codebase actually is.

## What this is

A computer-use skill built on `cua-driver`, with three tasks: Calculator
(zero vision, Layer 2a), VS Code (Electron/CDP), MS Paint (genuine
vision). Full architecture and per-task reasoning is in `README.md` --
read that first for the *why*; this doc is for the *what to check before
trusting it*.

## What has and hasn't been verified

**Verified on a real Windows 11 machine (cua-driver v0.5.7):**
- `llm_gatewayV9` boots cleanly (`uv sync` + `uv run python main.py`).
- `code/` installs cleanly via `uv sync` (pyproject.toml added to repo).
- cua-driver v0.5.7 installs on Windows 11 via the PowerShell script.
- **Task 1 (Calculator) completes successfully**: `5000000*8.5/100/12 = 35,416.66666666667`.
  Confirmed on first real run. Key runtime fixes needed (all now in code):
  - `launch_app` for Win11 packaged apps returns a stub pid that redirects.
    Fixed: title-based window search fallback in `driver.find_window_by_title`.
  - `press_key` / `type_text` are ignored by UWP apps (PostMessage never
    reaches XAML input stack). Fixed: Task 1 clicks buttons via
    element_index (UIA InvokePattern) instead.
  - cua-driver v0.5+ returns plain-text confirmations for action tools
    (not JSON). Fixed: `driver.call()` gracefully handles non-JSON exit-0.
  - `launch_app` response now includes a `windows` array; revised code reads
    window_id from it then validates via `list_windows`.

- **Task 2 (VS Code) completes successfully**: scanned `assets/sample.py`,
  added LLM-generated docstrings to all undocumented functions/methods,
  saved the file, and verified docstring coverage via `assets/analyze.py`
  in the integrated terminal.

- **Task 3 (MS Paint) completes successfully**: drew a five-pointed star
  on the canvas, vision verdict confirmed `looks_like_target: True`,
  saved result to `code/assets/mspaint_output.png`. Key runtime fixes
  encountered and resolved:
  - `screenshot()` must decode `screenshot_png_b64` from the JSON response
    (cua-driver v0.5.7 on Windows does not write `screenshot_out_file`).
  - `drag()` requires `from_x/from_y/to_x/to_y` parameter names in the
    JSON (not `x1/y1/x2/y2`).
  - New Paint's XAML canvas silently drops PostMessage; `dispatch="foreground"`
    (SendInput) is required.
  - `dispatch="foreground"` takes screen-absolute coordinates; canvas
    offsets back-calculated from observed cursor position.
  - Re-scanning (`action.scan()`) after clicking the Five-point star button
    resets the shape selection; skip the post-click scan.
  - `start_recording()` hooks block SendInput; call `stop_recording()`
    before the draw drag and `start_recording()` after.

**Remaining open item:**

### `page` tool's action enum (`task2_vscode.py`)

Only one action variant (`"click"`) has a worked example in the source
material. Task 2 deliberately uses only that one. If extending CDP usage
later, run `cua-driver describe page` first.

## How to actually run this

```bash
cd computer-use-agent
cp .env.example .env        # fill in at least GEMINI_API_KEY

# Install with uv
cd code
uv sync                     # creates .venv, installs from pyproject.toml
uv run python run_all.py calculator   # start with the lowest-risk task first
```

If `python run_all.py calculator` fails before ever calling `cua-driver`,
the problem is environment/imports, not the driver integration -- check
that first. If it fails *inside* a `driver.call(...)`, that's where
items 1-5 above come in.

## Debugging a stuck run

- `cua-driver shutdown` is the documented emergency stop -- kills the
  daemon, the agent stops within a second.
- Every run's trajectory lives in `trajectories/<task_name>/`, including
  a `run_log.jsonl` (this project's own event log, separate from
  cua-driver's own trajectory format) with one line per significant
  step. Read that first when a run produces a surprising result.
- `replay_trajectory` (wrapped in `driver.py`) replays a recorded run
  against the same starting UI state -- useful for confirming a fix
  actually changes the outcome rather than just not crashing.

## Recording the YouTube demo

The assignment requires the agent-cursor overlay visible during the
live demo. This is a screen-recording setting, not something in this
codebase -- enable Windows' pointer trail or a click-highlight tool
before recording, since `cua-driver`'s synthetic clicks don't show any
visual indicator of their own.

## Things deliberately left out of scope

- **No wiring into an existing Session-9-style orchestrator
  (`skills.py` dispatch).** This project is self-contained. If you want
  to fold it into a larger runtime later, the driver guide's own
  description of that integration is "one line" (`if skill.name ==
  "computer": ...`) -- this repo's `run_all.py` is structured so that
  line would just call into it, but no such orchestrator exists in this
  repo and none of this code assumes one does.
- **No fresh local user account.** The driver guide recommends one for
  "any enterprise effort" touching important data; this is a personal
  laptop running against test files only, so that setup step was
  explicitly skipped by request.
- **No Flask/web dashboard.** Earlier drafts of this project had one;
  it was dropped in favour of the plain CLI scripts here, closer to the
  reference `lab-lens-browser-automation` pattern and with less to
  maintain for what's fundamentally a one-shot demo, not a long-running
  service.
