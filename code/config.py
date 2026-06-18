"""Shared configuration for the computer-use agent.

Loads a single .env file from the repo root (the same file llm_gatewayV9
reads its own provider keys from -- see gateway.py for why one shared
.env works for both).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CODE_DIR.parent
TRAJECTORIES_DIR = REPO_ROOT / "trajectories"
ASSETS_DIR = CODE_DIR / "assets"


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if k and k not in os.environ:
            os.environ[k] = v


_load_env(REPO_ROOT / ".env")

# --- cua-driver ---------------------------------------------------------
CUA_DRIVER_BIN = os.getenv("CUA_DRIVER_BIN", "cua-driver")
DAEMON_START_WAIT_S = 0.5

# --- LLM judgment model (Layer 2b) --------------------------------------
# Left unset by default so the gateway's own failover order
# (llm_gatewayV9/.env LLM_ORDER) decides -- per the "config edit, not
# code edit" principle, pin a model by editing agent_routing.yaml instead
# of hardcoding a provider here.
JUDGE_AGENT = "computer"

# --- Task 1: Calculator ---------------------------------------------------
CALCULATOR_APP_NAME = os.getenv("CALCULATOR_APP_NAME", "Calculator")
CALCULATOR_EXPRESSION = os.getenv("CALCULATOR_EXPRESSION", "5000000*8.5/100/12")
CALCULATOR_EXPECTED_RESULT = "35,416.666666666664"  # for human sanity-check only;
# the task verifies via the AX tree at runtime, never a hardcoded compare.

# --- Task 2: VS Code (Electron) ------------------------------------------
VSCODE_APP_NAME = os.getenv("VSCODE_APP_NAME", "Visual Studio Code")
VSCODE_BUNDLE_ID = os.getenv("VSCODE_BUNDLE_ID", "com.microsoft.VSCode")
ELECTRON_DEBUG_PORT = int(os.getenv("ELECTRON_DEBUG_PORT", "9222"))


def _find_vscode_exe() -> str:
    """Resolve the VS Code executable on Windows.

    The PATH shim (`code` / `code.cmd`) is a batch file that subprocess
    cannot launch without shell=True.  Instead we resolve the .cmd shim to
    the real Code.exe sitting one directory above its bin/ folder, then fall
    back to common install locations.
    """
    shim = shutil.which("code.cmd") or shutil.which("code")
    if shim:
        p = Path(shim)
        if p.suffix.lower() in (".cmd", ".bat"):
            candidate = p.parent.parent / "Code.exe"
            if candidate.exists():
                return str(candidate)
    for loc in [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe",
        Path(r"C:\Program Files\Microsoft VS Code\Code.exe"),
    ]:
        if loc.exists():
            return str(loc)
    return "code"


VSCODE_EXE = os.getenv("VSCODE_EXE", _find_vscode_exe())
SAMPLE_PY_PATH = ASSETS_DIR / "sample.py"
AUDIT_OUTPUT_PATH = ASSETS_DIR / "docstring_audit.md"

# --- Task 3: MS Paint (vision) -------------------------------------------
PAINT_APP_NAME = os.getenv("PAINT_APP_NAME", "Paint")
PAINT_BIN = os.getenv("PAINT_BIN", "mspaint.exe")
PAINT_DRAW_TARGET = os.getenv("PAINT_DRAW_TARGET", "a 5-pointed star")
PAINT_SAVE_PATH = os.getenv(
    "PAINT_SAVE_PATH", str(ASSETS_DIR / "mspaint_output.png")
)
PAINT_MAX_STEPS = int(os.getenv("PAINT_MAX_STEPS", "12"))

# --- Recording -------------------------------------------------------------
def trajectory_dir(run_id: str) -> Path:
    d = TRAJECTORIES_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d
