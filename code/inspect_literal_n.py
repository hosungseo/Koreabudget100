#!/usr/bin/env python3
"""Report files that still contain literal backslash-n glue after colons."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "code"


def main() -> None:
    pat = re.compile(r"(?::|else|try|except[^\n]*|finally)\\n")
    found = 0
    for path in sorted(ROOT.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = []
        for i, line in enumerate(text.splitlines(), 1):
            if ":\\n" in line or "else:\\n" in line or "try:\\n" in line:
                hits.append((i, line[:160]))
            elif "\\n" in line and any(k in line for k in ("if ", "except", "else", "try", "for ", "while ")):
                # only report dense glue, not normal string literals like "\\n".join
                if re.search(r":\\n", line):
                    hits.append((i, line[:160]))
        if hits:
            found += 1
            print(f"FILE {path.name}")
            for i, line in hits[:20]:
                print(f"  L{i}: {line}")
    print(f"summary files_with_colon_backslash_n={found}")


if __name__ == "__main__":
    main()
