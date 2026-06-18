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

import task1_calculator
import task2_vscode
import task3_mspaint

TASKS = {
    "calculator": task1_calculator.run,
    "vscode": task2_vscode.run,
    "mspaint": task3_mspaint.run,
}


def main() -> None:
    requested = sys.argv[1:] or list(TASKS.keys())
    unknown = [t for t in requested if t not in TASKS]
    if unknown:
        print(f"Unknown task(s): {unknown}. Choose from: {list(TASKS.keys())}")
        sys.exit(1)

    results = []
    for name in requested:
        print(f"\n=== Running {name} ===")
        try:
            results.append(TASKS[name]())
        except Exception as e:
            print(f"[{name}] FAILED: {e}")
            results.append({"task": name, "error": str(e)})

    print("\n=== Summary ===")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
