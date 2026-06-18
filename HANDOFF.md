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

**Verified by actually running it in a sandbox:**
- `llm_gatewayV9` boots cleanly with zero API keys configured (graceful
  empty-provider degradation, not a crash) -- confirmed via `python3
  main.py` and hitting `/v1/routers`, `/v1/providers`, `/v1/capabilities`.
- `code/gateway.py`'s path math (`Path(__file__).resolve().parents[1] /
  "llm_gatewayV9"`) correctly resolves to the bundled gateway folder
  given this repo's actual layout (`code/` and `llm_gatewayV9/` as
  siblings at repo root).
- All `.py` files in `code/` parse without syntax errors
  (`ast.parse()`'d individually).
- `code/assets/analyze.py` correctly finds 5 undocumented functions in
  `code/assets/sample.py` (confirmed by actually running it).
- The Task 3 star geometry (5 points around a circle, connected
  pentagram-style) produces a sensible coordinate set (confirmed by
  actually computing it).

**Not yet verified -- there is no Windows machine, no `cua-driver`
binary, no MS Paint, and no VS Code in the sandbox this was built in.**
Everything below is reasoned from the driver guide's documented examples,
not from an actual run. Treat all of it as the first thing to check when
something breaks, in roughly this priority order:

### 1. `launch_app`'s Windows JSON schema (`driver.py: launch_app()`)

The guide's only worked examples are macOS (`bundle_id`) and one
ambiguous VS Code Electron example that doesn't specify an OS. There is
no Windows-native example (a Calculator or Paint launch) anywhere in the
source material. Run this on the real machine first:

```
cua-driver describe launch_app
```

and compare against what `launch_app()` sends. If the real schema wants
something other than `name`/`bundle_id`/`path`, this is a one-function
fix -- everything downstream (window discovery, scanning, action
dispatch) is unaffected since they all just consume the returned `pid`.

### 2. The `page` tool's action enum (`driver.py: page()`, used in `task2_vscode.py`)

Only one example exists anywhere in the source material:
`{"action": "click", "selector": "..."}`. `task2_vscode.py` deliberately
uses only that one action, with the exact selector from the guide's own
example (`.tabs-container .tab.active`), specifically to avoid guessing
at action names that might not exist. If you want to extend Task 2's CDP
usage (e.g. reading editor text via DOM rather than the file-read this
project uses instead), run:

```
cua-driver describe page
```

first.

### 3. MS Paint version (`task3_mspaint.py`)

Windows 11 may launch the classic `mspaint.exe` or a Store-distributed
redesign depending on the build/update channel. Their toolbars differ in
AX layout, but this task never reads the toolbar's AX tree -- only the
canvas screenshot -- so this shouldn't actually matter. If it does turn
out to matter (e.g. the Store version sandboxes screenshot access
differently), that's worth a note back in this file.

### 4. The Save-As dialog's actual layout (`task3_mspaint.py`)

`perception.judge_action()` is asked to find the filename field and Save
button from the dialog's AX tree -- this is the one place in the whole
project that exercises the literal Layer 2b pattern (AX markdown + goal
-> cheap LLM -> `{"verdict": "act", "action": {...}}`) for real, so it's
worth watching closely on the first run. If the judgment call
consistently escalates instead of acting, the dialog's tree_markdown is
probably more cluttered than expected -- `perception.trim_tree()` is the
knob to adjust.

### 5. `bring_to_front` and `Enter`-as-equals in Calculator

Both are stated as working on Windows in the driver guide (no
Windows-specific traps listed for either, unlike the macOS
background-launch trap). Lowest-risk item on this list, included for
completeness.

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
