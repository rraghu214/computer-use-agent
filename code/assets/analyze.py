"""Docstring coverage checker for sample.py.

Run standalone (`python analyze.py`) -- this is what Task 2 executes
inside VS Code's integrated terminal as an objective, independently
computed check that the docstrings the agent inserted actually landed,
rather than trusting the editor state alone.

Deliberately uses only `ast` from the standard library so it has no
dependency on anything else in this project -- it needs to keep working
even if sample.py is opened in a bare VS Code window with nothing else
on the path.
"""
from __future__ import annotations

import ast
from pathlib import Path

SAMPLE_PATH = Path(__file__).parent / "sample.py"


def _has_docstring(node) -> bool:
    return ast.get_docstring(node) is not None


def analyze(path: Path = SAMPLE_PATH) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append((node.name, node.lineno, _has_docstring(node)))

    total = len(functions)
    with_doc = sum(1 for _, _, has in functions if has)
    without_doc = total - with_doc
    coverage = (with_doc / total * 100) if total else 100.0

    return {
        "functions": functions,
        "total_functions": total,
        "with_docstring": with_doc,
        "without_docstring": without_doc,
        "coverage_pct": round(coverage, 1),
    }


if __name__ == "__main__":
    result = analyze()
    print(f"TOTAL_FUNCTIONS={result['total_functions']}")
    print(f"WITH_DOCSTRING={result['with_docstring']}")
    print(f"WITHOUT_DOCSTRING={result['without_docstring']}")
    print(f"COVERAGE={result['coverage_pct']}")
    for name, lineno, has_doc in result["functions"]:
        marker = "OK" if has_doc else "MISSING"
        print(f"  line {lineno:>4}  {marker:7}  {name}")
