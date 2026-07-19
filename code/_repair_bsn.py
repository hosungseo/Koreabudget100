#!/usr/bin/env python3
"""Repair files flattened with literal backslash-n sequences."""
from __future__ import annotations

import py_compile
import sys
from pathlib import Path


def repair(path: Path) -> bool:
    raw = path.read_bytes()
    fixed = raw
    # colon + backslash + n  -> colon + real newline
    fixed = fixed.replace(b":\\n", b":\n")
    fixed = fixed.replace(b"else:\\n", b"else:\n")
    fixed = fixed.replace(b"try:\\n", b"try:\n")
    fixed = fixed.replace(b"finally:\\n", b"finally:\n")
    # common glued function separators
    fixed = fixed.replace(b"return None\\n\\n\\ndef ", b"return None\n\n\ndef ")
    fixed = fixed.replace(b"return None\\n\\ndef ", b"return None\n\ndef ")
    fixed = fixed.replace(b"return t\\n\\n\\ndef ", b"return t\n\n\ndef ")
    fixed = fixed.replace(b"return None\\n    return t", b"return None\n    return t")
    if fixed == raw:
        print(f"nochange {path}")
        return False
    path.write_bytes(fixed)
    py_compile.compile(str(path), doraise=True)
    print(f"repaired {path}")
    return True


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: _repair_bsn.py file.py [file.py ...]")
        return 2
    for arg in sys.argv[1:]:
        repair(Path(arg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
