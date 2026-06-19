"""CLI entrypoint.

    python run_all.py                # all three tasks, in order
    python run_all.py calculator      # just one
    python run_all.py vscode
    python run_all.py mspaint

Each task is independently recorded (see recorder.py) and independently
runnable -- there's no shared state between them beyond the gateway,
which auto-starts on first use either way.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gateway
import task1_calculator
import task2_vscode
import task3_mspaint

TASKS = {
    "calculator": task1_calculator.run,
    "vscode": task2_vscode.run,
    "mspaint": task3_mspaint.run,
}

# Maps CLI task name → RUN_ID used inside the task (for cost ledger lookup).
_TASK_SESSION = {
    "calculator": task1_calculator.RUN_ID,
    "vscode":     task2_vscode.RUN_ID,
    "mspaint":    task3_mspaint.RUN_ID,
}


def main() -> None:
    requested = sys.argv[1:] or list(TASKS.keys())
    unknown = [t for t in requested if t not in TASKS]
    if unknown:
        print(f"Unknown task(s): {unknown}. Choose from: {list(TASKS.keys())}")
        sys.exit(1)

    results = []
    for name in requested:
        print(f"\n{'='*60}")
        print(f"  Running: {name}")
        print(f"{'='*60}")
        try:
            results.append(TASKS[name]())
        except Exception as e:
            print(f"[{name}] FAILED: {e}")
            results.append({"task": name, "error": str(e)})

    print(f"\n{'='*60}")
    print("  RESULTS SUMMARY")
    print(f"{'='*60}")
    for r in results:
        task = r.get("task", "?")
        if "error" in r:
            print(f"  {task}: FAILED — {r['error']}")
        else:
            # Print task-specific success fields concisely.
            if "result" in r:
                print(f"  {task}: result={r['result']}")
            elif "documented" in r:
                print(f"  {task}: documented={r['documented']}/{r.get('total_undocumented_found','?')}")
            elif "looks_like_target" in r:
                print(f"  {task}: vision={r['looks_like_target']}  save_path={Path(r.get('save_path','')).name}")
            else:
                print(f"  {task}: {r}")

    if len(requested) > 1:
        print(f"\n{'='*60}")
        print("  GRAND TOTAL — LLM Cost Across All Tasks")
        print(f"{'='*60}")
        for name in requested:
            gateway.print_cost_summary(_TASK_SESSION[name])


if __name__ == "__main__":
    main()
