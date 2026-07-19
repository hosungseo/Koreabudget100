#!/usr/bin/env python3
"""Run a Python file after validating it has real newlines.

Usage:
  python3 code/safe_py.py code/some_script.py [args...]

Prefer write/edit tools for multi-line Python, then run the file.
Avoid python3 -c / fragile heredoc one-liners that can mangle newlines into
literal backslash-n sequences.
"""
from __future__ import annotations

import py_compile
import runpy
import sys
from pathlib import Path


def looks_mangled(text: str) -> bool:
    if ":\\n" in text or "else:\\n" in text or "try:\\n" in text:
        return True
    if text.count("\n") < 3 and text.count("\\n") >= 3:
        return True
    return False


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: safe_py.py <script.py> [args...]", file=sys.stderr)
        return 2

    script = Path(sys.argv[1]).expanduser().resolve()
    if not script.exists():
        print(f"missing: {script}", file=sys.stderr)
        return 2

    text = script.read_text(encoding="utf-8", errors="replace")
    if looks_mangled(text):
        print(
            f"refusing mangled script (literal backslash-n detected): {script}",
            file=sys.stderr,
        )
        return 3

    try:
        py_compile.compile(str(script), doraise=True)
    except py_compile.PyCompileError as err:
        print(f"compile failed: {err}", file=sys.stderr)
        return 4

    sys.argv = [str(script), *sys.argv[2:]]
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
