#!/usr/bin/env python3
"""Run OpenDataLoader on parser A/B sample PDFs."""
from __future__ import annotations

import time
from pathlib import Path

import opendataloader_pdf as odl

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "parser_ab" / "samples"
OUT = ROOT / "data" / "parser_ab" / "odl"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(SAMPLES.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"no sample pdfs in {SAMPLES}")
    for pdf in pdfs:
        t0 = time.time()
        try:
            odl.convert(
                str(pdf),
                output_dir=str(OUT),
                format=["markdown", "json", "text"],
                quiet=True,
                table_method="cluster",
                reading_order="xycut",
            )
            dt = time.time() - t0
            (OUT / f"{pdf.stem}.time").write_text(f"real {dt:.3f}\n", encoding="utf-8")
            print(f"ok {pdf.name} {dt:.2f}s")
        except Exception as e:
            dt = time.time() - t0
            (OUT / f"{pdf.stem}.err").write_text(repr(e), encoding="utf-8")
            print(f"ERR {pdf.name} {e!r} {dt:.2f}s")
    print("files:")
    for pth in sorted(OUT.iterdir()):
        print(pth.name, pth.stat().st_size)


if __name__ == "__main__":
    main()
