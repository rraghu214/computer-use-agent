# Simple Notes — How the Computer-Use Agent Works

Plain-language guide to what files run, in what order, and what each one does.

---

## The Big Picture

```
You type:  uv run python run_all.py
              │
              └── run_all.py        ← the entry point; runs all 3 tasks in order
                    ├── task1_calculator.py
                    ├── task2_vscode.py
                    └── task3_mspaint.py
                          │
                    Every task shares these support modules:
                          ├── driver.py       ← talks to cua-driver (Windows AX APIs)
                          ├── gateway.py      ← talks to the LLM gateway service
                          ├── planner.py      ← Layer 1: breaks goal into steps
                          ├── perception.py   ← Layer 2: reads and interprets UI state
                          ├── action.py       ← Layer 3: scan → act → verify loop
                          ├── recovery.py     ← Layer 4: handles errors and empty trees
                          ├── vision.py       ← Layer 5: screenshot + vision LLM
                          └── recorder.py     ← wraps start_recording/stop_recording
```

---

## What Each Support File Does

| File | Plain-English Role |
|---|---|
| `driver.py` | Your hands and eyes. Wraps every cua-driver command: launch apps, click buttons, drag, take screenshots, record. |
| `gateway.py` | Your phone to the AI. Auto-starts the LLM gateway server, routes chat and vision calls to free-tier providers (Gemini, Groq). Also prints the cost/token summary after each task. |
| `planner.py` | Your to-do list maker. Given a goal, returns an ordered list of steps. For these 3 tasks the list is fixed (no LLM needed). |
| `perception.py` | Your brain for reading the UI. `extract_direct()` reads a value from the AX tree. `judge_action()` sends the AX tree + question to an LLM and gets a decision back. |
| `action.py` | Your discipline enforcer. `scan()` reads the current UI state. `act()` takes one action. `verify()` confirms the result. Never acts on a stale scan. |
| `recovery.py` | Your safety net. If the AX tree is empty after launching, tries bring-to-front and rescans once. |
| `vision.py` | Your camera + AI eyes. Takes a screenshot, sends it to a vision LLM with a question, gets a structured answer back. |
| `recorder.py` | Your security camera. Wraps `start_recording`/`stop_recording` so every run produces a trajectory log. |
| `config.py` | All constants in one place: app names, file paths, ports, LLM settings. |

---

## Task 1 — Calculator

**Goal:** compute `5000000 × 8.5 ÷ 100 ÷ 12` and return the result.

```
run_all.py
  └── task1_calculator.run()
        │
        ├── planner.decompose()           Layer 1: returns fixed subgoal list (free)
        │
        ├── recorder.recorded_run()       starts trajectory recording
        │
        ├── driver.launch_app("Calculator")
        │     └── calc.exe opens on screen
        │
        ├── action.scan(pid, window_id)   Layer 2a: reads AX tree
        │     └── returns tree_markdown with all button names + element_index values
        │
        ├── _build_button_map()           parses tree → {button_name: element_index}
        │     └── e.g. {"five": 12, "multiply by": 20, "equals": 7, ...}
        │
        ├── driver.click(..., element_index=...)   × 17 clicks
        │     └── UIA InvokePattern — works on Win11 Calculator (PostMessage doesn't)
        │
        ├── action.verify()               waits until display shows a result
        │
        ├── perception.extract_direct()   Layer 1: reads "Display is 35,416.67" from tree
        │
        ├── gateway.print_cost_summary()  prints: "no LLM calls recorded"
        │
        └── returns {"result": "35,416.66666666667"}
```

**Layers used:** 1 (goal) + 2a (AX tree) + 3 (scan-act-verify)
**Layers NOT used:** 2b (LLM judgment), 4 (recovery), 5 (vision)
**LLM calls: 0. Vision calls: 0.**

---

## Task 2 — VS Code

**Goal:** find all TODO-stub docstrings in `sample.py` and replace with real ones.

```
run_all.py
  └── task2_vscode.run()
        │
        ├── planner.decompose()           Layer 1: fixed subgoal list (free)
        │
        ├── recorder.recorded_run()       starts trajectory recording
        │
        ├── subprocess.Popen(VSCODE_EXE, sample.py)
        │     └── VS Code opens with sample.py in a tab
        │     └── stdout/stderr suppressed (no verbose Electron logs in console)
        │
        ├── driver.find_window_by_title() finds VS Code window pid + window_id
        │
        ├── driver.page(..., "click", ".tabs-container .tab.active")
        │     └── CDP click on the active tab (Electron path)
        │     └── Non-fatal: fails on existing VS Code without debug port
        │
        ├── perception.read_file(sample.py)   Layer 1: reads file from disk
        │
        ├── _find_undocumented(source)    Layer 1: AST walk
        │     ├── ast.parse() → walk every FunctionDef / AsyncFunctionDef
        │     ├── detect TODO stubs: docstring.upper().startswith("TODO")
        │     └── returns list of {name, def_line, insert_line, snippet, replace=True}
        │         found: [total_interest, amortisation_schedule, __init__,
        │                 total_payable, LoanSummary.total_interest]
        │
        ├── _draft_docstring() × 5        Layer 2b: one LLM call per function
        │     ├── gateway.LLM().chat(snippet, system=DOCSTRING_SYSTEM, max_tokens=1000)
        │     ├── gateway routes to Gemini (free tier)
        │     └── returns e.g. '"""Calculate total interest paid over the loan term."""'
        │
        ├── (write docstrings to file, bottom→top to preserve line numbers)
        │     └── SAMPLE_PY_PATH.write_text(modified)
        │
        ├── driver.hotkey([ctrl, shift, p])  "Open Command Palette"
        │   driver.hotkey([ctrl, v])         paste "revert file"
        │   driver.press_key(Return)         VS Code reloads the file from disk
        │     └── Updated docstrings now visible in VS Code editor
        │
        ├── subprocess.run(analyze.py)    Layer 1 verify: AST coverage check
        │
        ├── _find_undocumented(after)     re-parse → 0 stubs remaining
        │
        ├── gateway.print_cost_summary()  prints 5 LLM rows + total tokens
        │
        └── returns {"documented": 5, "total_undocumented_found": 5}
```

**Layers used:** 1 (goal + AST perception) + 2b (LLM docstring) + 3 (scan-act-verify via file I/O)
**Layers NOT used:** 2a (Electron has no AX tree), 4 (no recovery needed), 5 (vision)
**LLM calls: 5. Vision calls: 0.**

---

## Task 3 — MS Paint

**Goal:** draw a five-pointed star, verify it with vision, save it.

```
run_all.py
  └── task3_mspaint.run()
        │
        ├── timestamp = datetime.now().strftime("%d%m%y_%H%M")
        │     └── paint_save_path = "mspaint_output_190626_1423.png"
        │
        ├── planner.decompose()           Layer 1: fixed subgoal list (free)
        │
        ├── recorder.recorded_run()       starts trajectory recording
        │
        ├── driver.launch_app("mspaint")
        │     └── MS Paint opens on screen
        │
        ├── action.scan(pid, window_id)   Layer 2a: reads AX tree
        │     └── searches for "Five-point star" button
        │
        ├── _find_element_index(tree_md, "Five-point star")
        │     └── returns element_index=38
        │
        ├── driver.click(..., element_index=38)
        │     └── shape tool armed (no re-scan: UIA scan would reset shape selection)
        │
        ├── driver.stop_recording()       ← must pause before SendInput draw
        │
        ├── driver.list_windows(pid)      get live window position
        │   compute: x1=wx+765, y1=wy+472, x2=wx+1156, y2=wy+720
        │
        ├── driver.bring_to_front()       MS Paint must be foreground for SendInput
        │
        ├── driver.drag(..., dispatch="foreground")   Layer 3 Action
        │     └── SendInput mouse drag draws the star shape on the XAML canvas
        │     └── PostMessage (default) would be silently ignored by new Paint
        │
        ├── driver.start_recording()      ← resume after draw
        │
        ├── vision.capture(pid, window_id, "mspaint_drawn.png")
        │     └── takes screenshot, saves to assets/
        │
        ├── vision.ask_vision(drawn_path, "Does this show a five-pointed star?")
        │     │                             Layer 5: Vision LLM call
        │     ├── gateway.vision(image_data_url, prompt, schema=_VERIFY_SCHEMA)
        │     └── returns {looks_like_target: True, feedback: "star visible"}
        │
        ├── (if False: retry drag once, bounded by PAINT_MAX_STEPS)
        │
        ├── driver.stop_recording()       pause for save dialog interaction
        ├── driver.hotkey([ctrl, s])      trigger Save As (background PostMessage — OK for keys)
        ├── clip.exe ← paste save path    set clipboard to timestamped filename
        ├── PowerShell SendKeys           Ctrl+A, Ctrl+V, Enter → interact with dialog
        ├── driver.hotkey([Escape])       dismiss any residual dialog
        │
        ├── shutil.copy2(drawn_path, paint_save_path)   guaranteed artifact copy
        ├── driver.start_recording()      resume
        │
        ├── gateway.print_cost_summary()  prints 1 vision LLM row + total tokens
        │
        └── returns {looks_like_target: True, save_path: "mspaint_output_190626_1423.png"}
```

**Layers used:** 1 (goal) + 2a (shape button) + 3 (scan-act-verify) + 4 (retry if star not found) + 5 (vision confirm)
**LLM calls: 0. Vision calls: 1.**

---

## How Layers Map to Files

```
   ASSIGNMENT LAYER          →   FILE           →   KEY FUNCTION(S)
   ──────────────────────────────────────────────────────────────────
   Layer 1: Goal decomp      →   planner.py     →   decompose()
   Layer 2a: AX direct       →   perception.py  →   extract_direct()
   Layer 2b: AX + LLM        →   perception.py  →   judge_action()
                             →   task2_vscode   →   _draft_docstring()
   Layer 3: Action seq       →   action.py      →   scan(), act(), verify()
   Layer 4: Recovery         →   recovery.py    →   recover_from_precondition()
   Layer 5: Vision           →   vision.py      →   ask_vision(), capture()
   ──────────────────────────────────────────────────────────────────
   Shared infrastructure:
     LLM routing             →   gateway.py     →   LLM().chat(), vision()
     Windows UI control      →   driver.py      →   click(), drag(), hotkey(), ...
     Trajectory recording    →   recorder.py    →   recorded_run(), log_event()
     All constants           →   config.py      →   (paths, ports, app names)
```

---

## Common Questions

**Q: Why does Calculator use element_index clicks instead of type_text?**
New Windows 11 Calculator is a XAML/UWP app. It ignores PostMessage (which is
what `press_key` and `type_text` use internally). UIA InvokePattern (element_index
click) bypasses the message pump entirely and works reliably.

**Q: Why can't VS Code use the AX tree?**
VS Code is Electron — its entire UI is a Chromium web page. The accessibility tree
sees one opaque `AXWebArea` node with no children. There's nothing to scan or click.
The CDP (Chrome DevTools Protocol) path is the only way to interact with the DOM,
and it requires VS Code to be launched with `--remote-debugging-port`.

**Q: Why does Paint need foreground dispatch?**
New Windows 11 Paint uses a XAML/WinUI canvas control that ignores PostMessage
mouse events. `dispatch="foreground"` uses SendInput instead, which simulates
actual hardware mouse movement and reaches the canvas.

**Q: Why stop recording before the drag?**
cua-driver's trajectory recording hooks intercept SendInput events. If recording
is active during a foreground drag, the hooks consume the events before Paint
receives them, so nothing gets drawn. Stopping recording for just that one step
avoids the conflict.

**Q: Why copy mspaint_drawn.png as the save artifact?**
Paint's Save As dialog is a WinRT shell picker — it doesn't appear in
`list_windows` and can't be driven by `hotkey(foreground)` without UIAccess.
The PowerShell SendKeys approach works best-effort. The shutil.copy2 is a
guaranteed fallback: the output file always exists and contains the vision-
verified screenshot of what was drawn.
