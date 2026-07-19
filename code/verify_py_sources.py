#!/usr/bin/env python3
"""Compile-check project Python sources.

Also flags files that look mangled into one line with fake escaped newlines,
without false-positiving on detectors that intentionally mention that pattern.
"""
from __future__ import annotations

import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def looks_runtime_mangled(text: str) -> bool:
    """True only when the file body itself is flattened with fake newlines."""
    real_newlines = text.count("\n")
    # A healthy multi-line source is fine even if it contains the two-char
    # sequence backslash+n inside string literals/regexes.
    if real_newlines >= 10:
        return False
    # Flattened one-liner body with many escaped newlines.
    return text.count("\\n") >= 3


def main() -> int:
    code_dir = ROOT / "code"
    bad = []
    ok = 0
    for path in sorted(code_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        mangled = looks_runtime_mangled(text)
        try:
            py_compile.compile(str(path), doraise=True)
            if mangled:
                bad.append((path.name, "runtime_mangled_newlines"))
                print(f"BAD {path.name}: runtime_mangled_newlines")
            else:
                ok += 1
                print(f"ok {path.name}")
        except py_compile.PyCompileError as err:
            msg = str(err).splitlines()[-1]
            bad.append((path.name, msg))
            print(f"BAD {path.name}: {msg}")
    print(f"summary ok={ok} bad={len(bad)}")
    for name, msg in bad:
        print(f" - {name}: {msg}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
