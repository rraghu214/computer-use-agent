"""Bridge to llm_gatewayV9.

Auto-starts the gateway on its configured port if it is not already up,
then re-exports the V9 `LLM` client plus a `vision()` helper for the
typed `/v1/vision` shim that `client.py` does not wrap.

Every module that needs an LLM or vision call does:

    from gateway import LLM, ensure_gateway, vision
    ensure_gateway()
    ...

`ensure_gateway()` is called lazily, right before the first real call in
each function -- not once globally at startup. This mirrors how the
gateway is wired into the lab-lens-browser-automation project, whose
`code/gateway.py` this file is a direct adaptation of.
"""
from __future__ import annotations

import importlib.util as _importlib_util
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import httpx

# llm_gatewayV9/ sits as a sibling of this project's root, one level up
# from this file (code/gateway.py -> repo root -> llm_gatewayV9/).
GATEWAY_DIR = Path(__file__).resolve().parents[1] / "llm_gatewayV9"
GATEWAY_PORT = int(os.getenv("GATEWAY_V9_PORT", "8109"))
GATEWAY_URL = os.getenv("LLM_GATEWAY_V9_URL", f"http://localhost:{GATEWAY_PORT}")


def _is_up() -> bool:
    try:
        httpx.get(f"{GATEWAY_URL}/v1/routers", timeout=2.0)
        return True
    except Exception:
        return False


def ensure_gateway() -> None:
    """Start the V9 gateway if it is not already running. Idempotent."""
    if _is_up():
        return
    if not GATEWAY_DIR.exists():
        raise RuntimeError(
            f"llm_gatewayV9 not found at {GATEWAY_DIR}. It should be bundled "
            "as a sibling folder of code/ -- check the repo layout."
        )
    print(f"[gateway] launching llm_gatewayV9 from {GATEWAY_DIR}")
    try:
        subprocess.Popen(
            ["uv", "run", "main.py"],
            cwd=str(GATEWAY_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        # uv not on PATH -- fall back to a plain interpreter invocation.
        import sys
        subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=str(GATEWAY_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    for _ in range(45):
        time.sleep(1)
        if _is_up():
            print(f"[gateway] up on {GATEWAY_URL}")
            return
    raise RuntimeError(f"Gateway V9 failed to start within 45s. Check {GATEWAY_DIR}")


def shutdown_gateway() -> None:
    """Best-effort stop, for symmetry with ensure_gateway(). Not required
    on every run -- the gateway is harmless to leave running between tasks."""
    try:
        import psutil  # type: ignore
        for proc in psutil.process_iter(["pid", "cmdline"]):
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if "main.py" in cmdline and str(GATEWAY_DIR) in cmdline:
                proc.terminate()
    except ImportError:
        pass


# Load V9's client.py without polluting sys.path -- the gateway directory
# has its own schemas.py/db.py etc. that would shadow same-named modules
# in this project if the whole folder went on sys.path.
_client_path = GATEWAY_DIR / "client.py"
if _client_path.exists():
    _spec = _importlib_util.spec_from_file_location("llm_gatewayV9_client", _client_path)
    _mod = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    LLM = _mod.LLM
else:
    LLM = None  # importers should call ensure_gateway() first and recheck


def vision(
    image_data_url: str,
    prompt: str,
    *,
    system: Optional[str] = None,
    schema: Optional[dict[str, Any]] = None,
    schema_name: str = "out",
    model: Optional[str] = None,
    provider: Optional[str] = None,
    agent: Optional[str] = None,
    session: Optional[str] = None,
    max_tokens: int = 1024,
) -> dict:
    """Single-image vision call via the gateway's typed /v1/vision shim.

    This is the Layer 3 (vision fallback) entry point. `client.py` does not
    wrap /v1/vision yet, so this calls it directly with httpx -- still zero
    provider/routing logic on our side; the gateway forces routing to a
    vision-capable provider and does all failover.

    Returns the same shape as a /v1/chat response: `text`, `provider`,
    `model`, and `parsed` (the schema-validated object) if `schema` was given.
    """
    ensure_gateway()
    payload: dict[str, Any] = {
        "image": image_data_url,
        "prompt": prompt,
        "schema_name": schema_name,
        "max_tokens": max_tokens,
    }
    if system:
        payload["system"] = system
    if schema:
        payload["schema"] = schema
    if model:
        payload["model"] = model
    if provider:
        payload["provider"] = provider
    if agent:
        payload["agent"] = agent
    if session:
        payload["session"] = session
    r = httpx.post(f"{GATEWAY_URL}/v1/vision", json=payload, timeout=120)
    r.raise_for_status()
    return r.json()


def print_cost_summary(session: str) -> None:
    """Query the gateway's cost ledger for a session and print a human-readable summary.

    Called at the end of each task run so the console shows turns, tokens, and
    estimated cost without the caller having to know the gateway's URL or schema.
    """
    try:
        data = LLM().cost_by_agent(session=session)
        rows_flat = [(ag, r) for ag, rows in data.items() for r in rows]
        if not rows_flat:
            print(f"  [cost] session='{session}': no LLM calls recorded (deterministic path, zero LLM cost)")
            return
        total_in = sum(r.get("in_tok", 0) or 0 for _, r in rows_flat)
        total_out = sum(r.get("out_tok", 0) or 0 for _, r in rows_flat)
        total_dollars = sum(r.get("dollars", 0.0) or 0.0 for _, r in rows_flat)
        print(f"  ── LLM cost ledger ── session='{session}'")
        for ag, r in rows_flat:
            print(f"    [{ag}]  {r.get('provider','?')}/{r.get('model','?')}  "
                  f"in={r.get('in_tok', 0):,}  out={r.get('out_tok', 0):,} tok  "
                  f"${r.get('dollars', 0.0):.5f}  latency={r.get('latency_ms', 0)}ms")
        print(f"  TOTAL: {len(rows_flat)} LLM turn(s)  |  "
              f"{total_in:,} in + {total_out:,} out tokens  |  ${total_dollars:.5f}")
    except Exception as e:
        print(f"  [cost] unable to fetch ledger for '{session}': {e}")


__all__ = ["ensure_gateway", "shutdown_gateway", "LLM", "vision", "print_cost_summary", "GATEWAY_URL", "GATEWAY_DIR"]
