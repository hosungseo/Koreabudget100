#!/usr/bin/env python3
"""Extract ministry budget PDFs with kordoc (chunks + markdown).

Primary extract layer decided 2026-07-19 A/B:\n  kordoc --format chunks > OpenDataLoader md > pdftotext
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF_ROOT = ROOT / "data" / "raw" / "pdfs"
KORDOC_ROOT = ROOT / "data" / "raw" / "kordoc"
KORDOC_VERSION = "4.2.1"


def output_paths(pdf: Path, out_dir: Path, fmt: str, pages: str | None) -> tuple[Path, Path]:
    """Return collision-free output and metadata paths for one extraction."""
    if fmt not in {"chunks", "markdown"}:
        raise ValueError(fmt)
    page_suffix = ""
    if pages is not None:
        normalized_pages = pages.strip()
        if not re.fullmatch(r"\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*", normalized_pages):
            raise ValueError(f"invalid page range: {pages!r}")
        page_suffix = ".pages-" + normalized_pages.replace(",", "_")
    extension = "chunks.json" if fmt == "chunks" else "md"
    out = out_dir / f"{pdf.stem}{page_suffix}.{extension}"
    meta = out_dir / f"{pdf.stem}{page_suffix}.{fmt}.meta.json"
    return out, meta


def cache_is_valid(
    pdf: Path,
    out: Path,
    meta_path: Path,
    fmt: str,
    pages: str | None,
) -> bool:
    """Accept only a complete, versioned full-document extraction cache."""
    if pages is not None or not out.is_file() or not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        pdf_stat = pdf.stat()
        out_stat = out.stat()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    valid = (
        meta.get("returncode") == 0
        and meta.get("format") == fmt
        and meta.get("kordoc_version") == KORDOC_VERSION
        and meta.get("pages") is None
        and meta.get("pdf") == str(pdf)
        and meta.get("input_bytes") == pdf_stat.st_size
        and meta.get("input_mtime_ns") == pdf_stat.st_mtime_ns
        and meta.get("out") == str(out)
        and meta.get("out_bytes") == out_stat.st_size
        and out_stat.st_size >= 20
    )
    if valid and fmt == "chunks":
        pdf_pages = meta.get("pdf_pages")
        valid = (
            isinstance(pdf_pages, int)
            and pdf_pages > 0
            and meta.get("page_min") == 1
            and meta.get("page_max") == pdf_pages
        )
    return valid


def pdf_page_count(pdf: Path) -> int:
    """Return the authoritative PDF page count using Poppler's pdfinfo."""
    proc = subprocess.run(
        ["pdfinfo", str(pdf)],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        match = re.search(r"^Pages:\s*(\d+)\s*$", proc.stdout or "", re.MULTILINE)
        if match is not None:
            return int(match.group(1))
    raise RuntimeError(f"cannot determine PDF page count for {pdf}: {(proc.stderr or '')[-300:]}")


def chunk_page_stats(path: Path) -> dict[str, int | None]:
    """Summarize page provenance embedded in a kordoc chunks result."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as err:
        raise RuntimeError(f"invalid kordoc chunks JSON: {path}") from err
    if not isinstance(data, list):
        raise RuntimeError(f"kordoc chunks root must be a list: {path}")
    pages = [
        item.get("page")
        for item in data
        if isinstance(item, dict) and isinstance(item.get("page"), int)
    ]
    return {
        "page_min": min(pages) if pages else None,
        "page_max": max(pages) if pages else None,
        "pages_with_chunks": len(set(pages)),
    }


def write_json_atomic(path: Path, payload: dict) -> None:
    """Write metadata without exposing a partially written cache record."""
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def run_kordoc(pdf: Path, out_dir: Path, fmt: str, pages: str | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdf.resolve()
    if pages is not None:
        pages = pages.strip()
    out, meta_path = output_paths(pdf, out_dir, fmt, pages)

    if cache_is_valid(pdf, out, meta_path, fmt, pages):
        return out

    temp_suffix = ".chunks.json" if fmt == "chunks" else ".md"
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{pdf.stem}.kordoc-",
        suffix=temp_suffix,
        dir=out_dir,
    )
    os.close(fd)
    temp_out = Path(temp_name)
    # Let kordoc create its output rather than presenting an existing empty file.
    temp_out.unlink()

    cmd = [
        "npx",
        "-y",
        f"kordoc@{KORDOC_VERSION}",
        str(pdf),
        "-o",
        str(temp_out),
        "--format",
        fmt,
        "--silent",
    ]
    if pages:
        cmd.extend(["--pages", pages])

    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except Exception:
        temp_out.unlink(missing_ok=True)
        raise
    dt = time.time() - t0
    pdf_stat = pdf.stat()
    temp_bytes = temp_out.stat().st_size if temp_out.exists() else 0
    meta = {
        "pdf": str(pdf),
        "input_bytes": pdf_stat.st_size,
        "input_mtime_ns": pdf_stat.st_mtime_ns,
        "format": fmt,
        "kordoc_version": KORDOC_VERSION,
        "pages": pages,
        "seconds": round(dt, 3),
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-500:],
        "stderr_tail": (proc.stderr or "")[-500:],
        "out": str(out),
        "out_bytes": temp_bytes,
    }
    failure = proc.returncode != 0 or temp_bytes < 20
    if not failure and fmt == "chunks":
        try:
            meta.update(chunk_page_stats(temp_out))
            meta["pdf_pages"] = pdf_page_count(pdf)
            if pages is None:
                failure = meta["page_min"] != 1 or meta["page_max"] != meta["pdf_pages"]
                if failure:
                    meta["coverage_error"] = "full extraction does not span first through last PDF page"
        except Exception as err:
            meta["coverage_error"] = repr(err)
            failure = True
    if failure:
        temp_out.unlink(missing_ok=True)
        write_json_atomic(meta_path, meta)
        raise RuntimeError(f"kordoc failed for {pdf.name} fmt={fmt}: {meta}")
    temp_out.replace(out)
    meta["out_bytes"] = out.stat().st_size
    write_json_atomic(meta_path, meta)
    return out


def extract_one(
    pdf: Path,
    ministry_key: str,
    pages: str | None = None,
    chunks_only: bool = False,
) -> dict:
    out_dir = KORDOC_ROOT / ministry_key / pdf.stem
    chunks = run_kordoc(pdf, out_dir, "chunks", pages=pages)
    md = None if chunks_only else run_kordoc(pdf, out_dir, "markdown", pages=pages)
    info = {
        "ministry_key": ministry_key,
        "pdf": str(pdf.relative_to(PDF_ROOT)) if pdf.is_relative_to(PDF_ROOT) else str(pdf),
        "chunks_path": str(chunks),
        "chunks_bytes": chunks.stat().st_size,
    }
    if md is not None:
        info["markdown_path"] = str(md)
        info["markdown_bytes"] = md.stat().st_size
    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="append", default=[], help="specific pdf path(s)")
    ap.add_argument("--ministry", default="", help="mois|molit|motir when using --pdf")
    ap.add_argument("--pages", default=None, help="kordoc page range, e.g. 1-30 or 798-812")
    ap.add_argument("--all", action="store_true", help="all PDFs under data/raw/pdfs")
    ap.add_argument("--pilot-samples", action="store_true", help="parser_ab sample PDFs only")
    ap.add_argument(
        "--chunks-only",
        action="store_true",
        help="extract the primary chunks format only (recommended for full runs)",
    )
    args = ap.parse_args()

    if not shutil.which("npx"):
        raise SystemExit("npx not found")

    jobs = []
    if args.pilot_samples:
        sample_dir = ROOT / "data" / "parser_ab" / "samples"
        for pdf in sorted(sample_dir.glob("*.pdf")):
            ministry = "mois" if "mois" in pdf.name else "molit"
            jobs.append((pdf, ministry))
    elif args.pdf:
        ministry = args.ministry or "unknown"
        for pth in args.pdf:
            jobs.append((Path(pth).expanduser().resolve(), ministry))
    elif args.all:
        for key in ("mois", "molit", "motir"):
            d = PDF_ROOT / key
            if not d.exists():
                continue
            for pdf in sorted(d.glob("*.pdf")):
                if pdf.stat().st_size < 1000:
                    continue
                if pdf.read_bytes()[:4] != b"%PDF":
                    continue
                jobs.append((pdf, key))
    else:
        raise SystemExit("use --pilot-samples or --all or --pdf")

    results = []
    for pdf, ministry in jobs:
        print(f"extract {pdf} ministry={ministry} pages={args.pages}")
        try:
            info = extract_one(
                pdf,
                ministry,
                pages=args.pages,
                chunks_only=args.chunks_only,
            )
            print(
                "  ok",
                "chunks",
                info["chunks_bytes"],
                "md",
                info.get("markdown_bytes", "skipped"),
            )
            results.append({"ok": True, **info})
        except Exception as err:
            print("  ERR", err)
            results.append({"ok": False, "pdf": str(pdf), "error": repr(err)})

    out = KORDOC_ROOT / "extract_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)
    ok_n = sum(1 for r in results if r.get("ok"))
    print(f"summary ok={ok_n} fail={len(results)-ok_n}")
    return 0 if ok_n == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
