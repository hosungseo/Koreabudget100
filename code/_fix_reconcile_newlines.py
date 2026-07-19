#!/usr/bin/env python3
"""Legacy one-shot newline repair retained as a safe no-op verifier."""
from __future__ import annotations

import py_compile
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "reconcile_pdf_with_api.py"


def main() -> int:
    py_compile.compile(str(TARGET), doraise=True)
    print("compile_ok", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
