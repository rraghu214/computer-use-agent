# YouTube Script — Computer-Use Agent (3–5 min)

---

## INTRO (0:00–0:20)

Hey! Quick walkthrough of a Computer-Use Agent — a Python program that drives
real Windows desktop apps: Calculator, VS Code, and MS Paint. No browser, no
mocked UI — actual app windows opening on screen, controlled by code.

---

## THE IDEA (0:20–0:50)

Most software has an API. Calculator doesn't. Paint doesn't. They were built for
humans — buttons, canvases, text fields.

A computer-use agent solves this by doing what a human does: look at the screen,
decide what to click, click it. We use **cua-driver**, a Rust binary that exposes
Windows accessibility APIs as JSON commands we call from Python.

---

## THE FIVE-LAYER RULE (0:50–1:30)

The architecture has five layers. The key rule: **always use the cheapest layer
that gets the job done.**

1. **Goal decomposition** — break the goal into steps (free, no LLM)
2. **Perception 2a** — read the accessibility tree directly (zero LLM cost)
3. **Perception 2b** — accessibility tree + cheap LLM judgment
4. **Error recovery** — retry with bring-to-front when the tree is empty
5. **Vision fallback** — screenshot + vision LLM, ~10x the cost of 2b

Don't call a vision model if the accessibility tree already has the answer.

---

## TASK 1 — CALCULATOR (1:30–2:20)

Goal: compute `5000000 × 8.5 ÷ 100 ÷ 12` (an EMI calculation).

- Scan the AX tree → find button indices for digits and operators
- Click them in sequence via UIA InvokePattern
- Read `Display is 35,416.67` straight from the AX tree

**Result: 35,416.67. Zero LLM calls. Zero vision calls.**

---

## TASK 2 — VS CODE (2:20–3:20)

Goal: replace TODO placeholder docstrings in `sample.py` with real ones.

VS Code is Electron — no accessibility tree. Instead:
- Parse `sample.py` using Python's `ast` module → find 5 TODO stubs
- Call a cheap LLM (Gemini, free tier) once per function → get a real docstring
- Write the updated file to disk
- Tell VS Code to "Revert File" so the editor shows the change
- Verify by re-parsing the AST → 0 stubs remaining

**Result: 5/5 functions documented. Zero vision calls. 5 LLM calls.**

---

## TASK 3 — MS PAINT (3:20–4:20)

Goal: draw a five-pointed star, verify it's there, save it.

- Scan AX tree → find "Five-point star" button (element_index=38)
- Click it to arm the shape tool
- Drag on the canvas — using **SendInput** (foreground dispatch) because
  new Windows 11 Paint's canvas ignores the normal PostMessage path
- Take a screenshot, send to a vision LLM: "Does this show a star?" → True
- Save with timestamped filename (`mspaint_output_190626_1423.png`)

**Result: star drawn and verified. 1 vision call — the only one across all 3 tasks.**

---

## THE CASCADE RESULT (4:20–4:45)

| Task | LLM calls | Vision calls |
|---|---|---|
| Calculator | 0 | 0 |
| VS Code | 5 (docstrings) | 0 |
| MS Paint | 0 | 1 (canvas verify) |

Three tasks. Six total LLM calls. All on free-tier providers.
The gateway tracks every token and prints cost at the end of each run.

---

## CLOSING (4:45–5:00)

Full code on GitHub. Needs cua-driver on Windows 11 and one free LLM key.

The takeaway: pick the cheapest layer that answers each question.
Read the tree when it's there. Call an LLM when judgment is needed.
Screenshot only when nothing else can see what you need to see.

Thanks for watching!
