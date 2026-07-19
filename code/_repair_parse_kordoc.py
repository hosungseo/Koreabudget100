#!/usr/bin/env python3
"""One-shot repair for parse_pdfs_kordoc.py literal backslash-n glue."""
from __future__ import annotations

import py_compile
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "parse_pdfs_kordoc.py"


def main() -> int:
    raw = TARGET.read_bytes()
    fixed = raw
    # Replace common fake-newline glues (backslash + n)
    replacements = [
        (b":\\n", b":\n"),
        (b"return None\\n", b"return None\n"),
        (b"return t\\n", b"return t\n"),
        (b"continue\\n", b"continue\n"),
        (b"pass\\n", b"pass\n"),
        (b"\\n    if ", b"\n    if "),
        (b"\\n        return ", b"\n        return "),
        (b"\\n    return ", b"\n    return "),
        (b"\\n\\ndef ", b"\n\ndef "),
        (b"\\n\\n\\ndef ", b"\n\n\ndef "),
    ]
    for old, new in replacements:
        fixed = fixed.replace(old, new)

    if fixed == raw:
        print("nochange")
    else:
        TARGET.write_bytes(fixed)
        print("rewrote", TARGET)

    py_compile.compile(str(TARGET), doraise=True)
    print("compile_ok")
    # show remaining suspicious non-regex backslash-n
    text = TARGET.read_text(encoding="utf-8")
    bad = 0
    for i, line in enumerate(text.splitlines(), 1):
        if "\\n" not in line:
            continue
        # allow regex/raw strings
        if "re." in line or 'r"' in line or "r'" in line or "\\\\n" in repr(line):
            # still flag obvious control-flow glue
            if ":\\n" in line or "return None\\n" in line:
                print(f"BAD L{i}: {line[:180]}")
                bad += 1
            continue
        if any(tok in line for tok in (":\\n", "return None\\n", "\\n    ", "\\ndef")):
            print(f"BAD L{i}: {line[:180]}")
            bad += 1
    print("bad_lines", bad)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
