#!/usr/bin/env python3
"""Save base64 PDF chunks written by browser export helper."""

from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "raw" / "pdfs" / "browser_export_manifest.json"
OUT = ROOT / "data" / "raw" / "pdfs"


def main() -> None:
    if not MANIFEST.exists():
        raise SystemExit(f"missing {MANIFEST}")
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for item in items:
        rel = item["path"]
        b64_path = Path(item["b64_path"])
        out = OUT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        data = base64.b64decode(b64_path.read_text(encoding="utf-8"))
        out.write_bytes(data)
        print("wrote", out, len(data), data[:8])


if __name__ == "__main__":
    main()
