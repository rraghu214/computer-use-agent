# computer-use-agent

A computer-use skill that drives real desktop applications on Windows
through `cua-driver`, using a free-tier multi-provider LLM gateway
(`llm_gatewayV9`, bundled in this repo) for every judgment and vision
call. No paid APIs, no third-party agentic frameworks.

## Repo layout

```
computer-use-agent/
├── llm_gatewayV9/      bundled LLM gateway (FastAPI service, port 8109)
└── code/
    ├── gateway.py        bridge: auto-starts the gateway, exposes LLM + vision()
    ├── config.py         paths, ports, per-task constants, .env loading
    ├── driver.py         cua-driver CLI wrapper
    ├── planner.py        Layer: goal decomposition
    ├── perception.py     Layer: perception interpretation
    ├── action.py         Layer: action sequencing (scan-act-verify)
    ├── recovery.py       Layer: error recovery
    ├── vision.py         Layer: vision fallback
    ├── recorder.py        start_recording/stop_recording wrapper
    ├── task1_calculator.py
    ├── task2_vscode.py
    ├── task3_mspaint.py
    ├── run_all.py         CLI entrypoint
    └── assets/            sample.py, analyze.py for the Task 2 demo
```

See `HANDOFF.md` for the things worth verifying before/while running this
on a real machine, and for picking the project back up in Claude Code.

## Setup

```bash
cp .env.example .env        # fill in at least one LLM provider key

# Install dependencies with uv (https://docs.astral.sh/uv/)
cd code
uv sync                     # creates .venv and installs from pyproject.toml

# The gateway auto-starts on first use; if you want to install it separately:
cd ../llm_gatewayV9
uv sync                     # uses pyproject.toml already present there

# Run tasks
cd ../code
uv run python run_all.py           # runs all three tasks, or:
uv run python run_all.py calculator
uv run python run_all.py vscode
uv run python run_all.py mspaint
```

The gateway starts itself on first use (`gateway.ensure_gateway()`); you
don't need to run it separately. `cua-driver` itself must already be
installed and on PATH -- this project only wraps it.

## Architecture: the five layers

`cua-driver` gives perception and action -- launching apps, walking
accessibility trees, synthesising clicks/keystrokes, screenshots,
recording. It does **not** plan, interpret what it perceives, recover
from errors, or do vision. Those five layers are what this project
builds on top, each in its own module so the cascade discipline is
visible rather than folded into the three task scripts:

| Layer | Module | What it does here |
|---|---|---|
| Goal decomposition | `planner.py` | Maps a goal to ordered subgoals. All three tasks use the free path (a known, fixed subgoal list, zero LLM cost) since the steps are well understood at write-time; the LLM-decompose path exists for free-text goals. |
| Perception interpretation | `perception.py` | `extract_direct()` reads values straight out of AX markdown (zero LLM). `judge_action()` is the Layer-2b workhorse: AX markdown + goal -> a cheap text model -> a structured `{"verdict": "act", "action": {...}}` or `{"verdict": "escalate", ...}`. |
| Action sequencing | `action.py` | `scan()` / `act()` / `verify()`, kept as separate calls on purpose so a stale `element_index` from a previous turn can never be reused -- the two invariants from the driver guide (scan before any indexed action; re-scan after every state-changing one) are enforced structurally, not by convention. |
| Error recovery | `recovery.py` | The "traps that look the same" from the driver guide: a cache-miss/empty-tree after launch gets one recovery attempt (bring-to-front, sleep, re-scan); a target that's *supposed* to have an empty tree (a canvas) raises immediately instead of retrying pointlessly. |
| Vision fallback | `vision.py` | Screenshot -> optional set-of-marks -> the gateway's typed `/v1/vision` endpoint -> a parsed verdict. Roughly 10x the per-turn cost of Layer 2b, used only where nothing else can do the job. |

This is a distinct concept from the *cost cascade* inside an individual
perception call (Layer 1 extract / Layer 2a deterministic / Layer 2b
AX+LLM / Layer 3 vision) -- the five layers above are the architecture;
the cost cascade is a decision made *within* the perception-interpretation
and vision-fallback layers about which is cheapest for a given step.

## The three tasks

### Task 1 -- Calculator (zero vision, Layer 2a)

Computes `5000000*8.5/100/12` (an EMI-style calculation) via a fixed
sequence of `press_key` calls -- no LLM in the loop at all, since both
the goal and the keystrokes needed to reach it are known up front.
Verification reads the result straight out of the AX tree
(`Display is <value>`) -- Layer 1, not Layer 2b, because there's nothing
to judge, only a value to read and compare.

**Cascade decision:** this task exists specifically to prove the
zero-vision floor of the cascade -- the assignment's "at least one task
completes with zero vision calls" constraint.

### Task 2 -- VS Code (Electron / CDP)

VS Code is Electron, so to the accessibility API it's a single opaque
`AXWebArea` -- there's no AX tree to scan no matter how the window is
activated. The fix is the documented one: relaunch with
`electron_debugging_port` and drive the DOM through the `page` tool.

This task reads `assets/sample.py`, finds functions missing docstrings
via a plain AST walk (Layer 1 -- the "tree" being filtered here is the
file's AST, not an AX tree, since none exists for Electron content), and
runs each through a cheap-LLM judgment call to draft a one-line
docstring. Insertion goes through VS Code's native "Go to Line" (Ctrl+G)
command plus typed keystrokes rather than CDP DOM scripting -- Monaco's
editor surface is virtualised and its internal selectors aren't
documented anywhere available here, so reaching into it with guessed CSS
selectors would be the fragile choice, not the careful one. The one
`page` call this task does make uses the exact selector from the driver
guide's own Electron example (`.tabs-container .tab.active`), kept
deliberately minimal rather than inventing further calls against an
unconfirmed action surface. After saving, `analyze.py` runs inside the
integrated terminal to independently re-check docstring coverage --
verification via a second, separate code path rather than trusting the
editor's own state.

**Cascade decision:** Electron is forced regardless of preference --
there is no AX-tree path available for this app at all.

### Task 3 -- MS Paint (genuine Layer 3 vision)

The fully reasoned version of why this counts as vision is in the
docstring at the top of `task3_mspaint.py`; the short version: MS
Paint's toolbar is real, AX-readable Win32 UI, but nothing in any
accessibility API describes the *pixel content* of the canvas. There's
no AX node for "a star is drawn here." That's the actual reason vision
is mandatory for this task -- not an empty `element_count`, but the
simple fact that no other perception channel for canvas content was
ever going to exist.

The star's geometry (five points around a circle, connected in a
pentagram pattern) is computed with plain trigonometry, not asked of a
vision model staring at a blank canvas -- there's nothing to perceive
yet at that point, only coordinates to compute. Vision is reserved for
afterward: a screenshot of the drawn result goes to the gateway's
`/v1/vision` endpoint with a yes/no-plus-feedback schema, asking whether
it actually looks like the target. One corrective redraw pass happens if
not, bounded by `PAINT_MAX_STEPS`.

Saving switches back to Layer 2b deliberately: the Save-As dialog is a
native Win32 dialog, fully AX-readable, so `perception.judge_action()`
drives it rather than continuing to use vision -- a direct illustration
of choosing the cheapest layer that can do the job, decided per step,
not per task.

**Cascade decision:** this is the assignment's required vision task, and
the one place where escalating to vision isn't a fallback from a failed
AX read -- it's the only channel that was ever available.

## Cost-ledger tagging

All gateway calls use `agent="computer"`, matching the driver guide's own
convention (`The cost ledger tags calls under agent: computer`), with
`session=<task name>` differentiating each task's calls for ledger
scoping. No provider is pinned in code -- if you want deterministic
routing, edit `llm_gatewayV9/agent_routing.yaml`, not the Python.

## Failure modes anticipated, not yet encountered

This build hasn't been run against the real Windows machine yet, so this
section is what's been reasoned through rather than what's actually
broken -- `HANDOFF.md` lists every specific thing worth verifying on the
first real run, and this section should be updated with what actually
happened once that run exists.

- **launch_app's exact Windows JSON schema is unconfirmed.** The driver
  guide's only worked examples use `bundle_id` (macOS) or a bare `name`
  (the VS Code Electron example, which doesn't specify an OS). `launch_app()`
  tries the documented shape first and falls back to a plain `subprocess.Popen`
  + `list_windows` poll if the tool call itself errors.
- **The `page` tool's action enum beyond `"click"` is unconfirmed** --
  only one worked example exists in the source material. Task 2 keeps
  its CDP usage to that one documented call rather than guessing at
  further action names.
- **MS Paint's actual launched version is unknown** -- Windows 11 may
  open the classic `mspaint.exe` or a Store-distributed redesign
  depending on the build. The toolbar's AX layout differs between them,
  but the canvas-is-a-blank-bitmap property (the actual reason this task
  needs vision) holds either way.
