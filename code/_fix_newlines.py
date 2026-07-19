#!/usr/bin/env python3
"""Detect/fix Python sources flattened with fake escaped newlines.

Failure mode:
  multi-line Python becomes one line containing backslash + n instead of
  real newlines, then:

    SyntaxError: unexpected character after line continuation character

This fixer only rewrites files that are actually flattened (few real newlines).
Detector source files that merely mention the pattern are left alone.
"""
from __future__ import annotations

import argparse
import py_compile
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRS = [ROOT / "code"]


def is_flattened_mangled(text: str) -> bool:
    real_nl = text.count("\n")
    esc_nl = text.count("\\n")
    if real_nl >= 10:
        return False
    if esc_nl < 3:
        return False
    # typical mangled control-flow glue in flattened bodies
    return (":\\n" in text) or ("else:\\n" in text) or ("try:\\n" in text)


def scan_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    issues: list[str] = []
    if is_flattened_mangled(text):
        issues.append("flattened_literal_backslash_n")
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as err:
        msg = str(err).splitlines()[-1]
        issues.append(f"compile_error: {msg}")
    return issues


def fix_file(path: Path, dry_run: bool = False) -> bool:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if not is_flattened_mangled(raw):
        # still allow compile-only recovery path? no - need mangled body
        # unless it fails compile AND has escaped newlines
        try:
            py_compile.compile(str(path), doraise=True)
            return False
        except py_compile.PyCompileError:
            if raw.count("\\n") < 3:
                return False

    fixed = raw.replace("\\r\\n", "\n")
    if fixed.count("\n") < 10 and fixed.count("\\n") >= 3:
        fixed = fixed.replace("\\n", "\n")
    else:
        fixed = re.sub(r":\\n(\s*)", r":\n\1", fixed)
        fixed = re.sub(r"\belse:\\n(\s*)", r"else:\n\1", fixed)
        fixed = re.sub(r"\btry:\\n(\s*)", r"try:\n\1", fixed)
        fixed = re.sub(r"\bfinally:\\n(\s*)", r"finally:\n\1", fixed)
        fixed = re.sub(r"\bexcept\s+([^:\n]+):\\n(\s*)", r"except \1:\n\2", fixed)

    if fixed == raw:
        return False

    tmp = path.with_suffix(path.suffix + ".fixing")
    tmp.write_text(fixed, encoding="utf-8")
    try:
        py_compile.compile(str(tmp), doraise=True)
    except py_compile.PyCompileError:
        tmp.unlink(missing_ok=True)
        return False

    if dry_run:
        tmp.unlink(missing_ok=True)
        return True

    tmp.replace(path)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    targets: list[Path] = []
    seeds = args.paths or DEFAULT_DIRS
    for seed in seeds:
        seed = seed if seed.is_absolute() else (Path.cwd() / seed)
        if seed.is_file():
            targets.append(seed)
        elif seed.is_dir():
            targets.extend(sorted(seed.rglob("*.py")))

    bad = 0
    fixed_n = 0
    for path in targets:
        if path.name.startswith(".") or "/venv/" in str(path):
            continue
        issues = scan_file(path)
        if not issues:
            continue
        bad += 1
        print(f"BAD {path}")
        for issue in issues:
            print(f"  - {issue}")
        if args.fix:
            ok = fix_file(path, dry_run=args.dry_run)
            suffix = " (dry-run)" if args.dry_run else ""
            print(f"  fix={'ok' if ok else 'skipped'}{suffix}")
            if ok and not args.dry_run:
                fixed_n += 1

    # Never report a successful repair merely because --fix was requested.
    # Re-scan every target after the attempted repairs so an unfixable syntax
    # error, a partial rewrite, or a dry-run with outstanding damage fails.
    remaining: list[tuple[Path, list[str]]] = []
    if args.fix:
        for path in targets:
            if path.name.startswith(".") or "/venv/" in str(path):
                continue
            issues = scan_file(path)
            if issues:
                remaining.append((path, issues))

        for path, issues in remaining:
            print(f"REMAINING {path}")
            for issue in issues:
                print(f"  - {issue}")

    print(
        f"summary bad={bad} fixed={fixed_n} "
        f"remaining={len(remaining)} scanned={len(targets)}"
    )
    if args.fix:
        return 1 if remaining else 0
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
