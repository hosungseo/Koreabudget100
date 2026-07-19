#!/usr/bin/env python3
from __future__ import annotations
import json, re, subprocess
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF_ROOT = ROOT / "data" / "raw" / "pdfs"
TEXT_ROOT = ROOT / "data" / "raw" / "pdf_text"
OUT = ROOT / "data" / "normalized"
ART = ROOT / "artifacts"

EXEC_PATTERNS = [
    (r"직접\s*수행|직접\s*집행|직접\s*시행", "직접"),
    (r"위탁|민간위탁|공공기관\s*위탁|출연", "위탁/출연"),
    (r"보조|보조금|지자체\s*보조|민간\s*보조", "보조"),
    (r"융자|이차보전", "융자"),
    (r"출자", "출자"),
    (r"기금\s*운용|기금", "기금"),
]

def extract_text(pdf, txt, max_pages=None):
    txt.parent.mkdir(parents=True, exist_ok=True)
    if txt.exists() and txt.stat().st_size > 1000 and txt.stat().st_mtime >= pdf.stat().st_mtime:
        return txt.read_text(encoding="utf-8", errors="replace")
    cmd = ["pdftotext", "-layout", str(pdf), str(txt)]
    if max_pages is not None:
        cmd = ["pdftotext", "-layout", "-f", "1", "-l", str(max_pages), str(pdf), str(txt)]
    subprocess.run(cmd, check=False, capture_output=True)
    if (not txt.exists()) or txt.stat().st_size < 50:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf))
        parts = []
        for i, page in enumerate(reader.pages):
            if max_pages is not None and i >= max_pages:
                break
            parts.append(page.extract_text() or "")
        text = chr(10).join(parts)
        txt.write_text(text, encoding="utf-8")
        return text
    return txt.read_text(encoding="utf-8", errors="replace")

def split_blocks(text):
    parts = re.split(r"\n(?=\s*(?:□|○|◯|◆|■|\d+\.\s|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+))", text)
    if len(parts) < 5:
        parts = re.split(r"\n{2,}", text)
    return [p.strip() for p in parts if p and p.strip()]

def guess_title(block):
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if not lines:
        return None
    for ln in lines[:8]:
        cleaned = re.sub(r"^[□○◯◆■\-\*\d\.\)\s]+", "", ln).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if 4 <= len(cleaned) <= 80 and not re.search(r"원$|백만원|억원|페이지|목차", cleaned):
            if cleaned in {"사업명", "사업개요", "산출근거", "추진체계"}:
                continue
            return cleaned
    return lines[0][:80]

def find_amounts(block):
    amts = re.findall(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?\s*(?:백만원|억원|원)?", block)
    amts += re.findall(r"\d+(?:\.\d+)?\s*(?:백만원|억원)", block)
    return amts[:12]

def find_exec_paths(block):
    found = []
    for pat, label in EXEC_PATTERNS:
        if re.search(pat, block):
            found.append(label)
    return sorted(set(found))

def extract_fields(block):
    fields = {}
    patterns = {
        "사업명": r"사업명\s*[:：]?\s*(.+)",
        "소관": r"소관\s*[:：]?\s*(.+)",
        "회계": r"회계\s*[:：]?\s*(.+)",
        "사업기간": r"사업기간\s*[:：]?\s*(.+)",
        "총사업비": r"총사업비\s*[:：]?\s*(.+)",
        "지원형태": r"지원형태\s*[:：]?\s*(.+)",
        "사업시행주체": r"사업시행주체\s*[:：]?\s*(.+)",
        "추진체계": r"추진체계\s*[:：]?\s*(.+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, block)
        if m:
            fields[key] = m.group(1).strip()[:200]
    return fields

def parse_pdf(pdf, ministry, max_pages=80):
    rel = pdf.relative_to(PDF_ROOT)
    txt = TEXT_ROOT / rel.with_suffix(".txt")
    text = extract_text(pdf, txt, max_pages=max_pages)
    blocks = split_blocks(text)
    cards = []
    exec_counter = Counter()
    for block in blocks:
        if len(block) < 80:
            continue
        score = 0
        if re.search(r"사업명|사업개요|산출근거|추진체계|지원형태|예산", block):
            score += 2
        if re.search(r"백만원|억원", block):
            score += 1
        if re.search(r"위탁|보조|직접|출연|융자", block):
            score += 1
        if score < 2:
            continue
        title = guess_title(block)
        exec_paths = find_exec_paths(block)
        for e in exec_paths:
            exec_counter[e] += 1
        cards.append({
            "ministry": ministry,
            "source_pdf": str(rel),
            "title": title,
            "exec_paths": exec_paths,
            "amounts": find_amounts(block),
            "fields": extract_fields(block),
            "snippet": re.sub(r"\s+", " ", block)[:400],
        })
    uniq = []
    seen = set()
    for c in cards:
        key = (c.get("title") or "", c.get("snippet", "")[:80])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return {
        "ministry": ministry,
        "pdf": str(rel),
        "chars": len(text),
        "blocks": len(blocks),
        "cards": uniq,
        "exec_path_counts": dict(exec_counter),
        "sample_titles": [c.get("title") for c in uniq[:15]],
    }

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)
    TEXT_ROOT.mkdir(parents=True, exist_ok=True)
    mapping = {"mois": "행정안전부", "molit": "국토교통부", "motir": "산업통상부"}
    targets = []
    for ministry_dir, ministry_name in mapping.items():
        d = PDF_ROOT / ministry_dir
        if not d.exists():
            continue
        for pdf in sorted(d.glob("*.pdf")):
            if pdf.stat().st_size < 1000 or pdf.read_bytes()[:4] != b"%PDF":
                continue
            targets.append((pdf, ministry_name))
    results = []
    all_cards = []
    for pdf, ministry in targets:
        print("parse", pdf.name, ministry, pdf.stat().st_size)
        max_pages = 120 if pdf.stat().st_size > 15_000_000 else None
        res = parse_pdf(pdf, ministry, max_pages=max_pages)
        results.append(res)
        all_cards.extend(res["cards"])
        print("  cards", len(res["cards"]), "exec", res["exec_path_counts"])
    by_ministry = defaultdict(list)
    for c in all_cards:
        by_ministry[c["ministry"]].append(c)
    summary = {
        "pdfs": [{
            "pdf": r["pdf"],
            "ministry": r["ministry"],
            "cards": len(r["cards"]),
            "exec_path_counts": r["exec_path_counts"],
            "sample_titles": r["sample_titles"],
        } for r in results],
        "total_cards": len(all_cards),
        "by_ministry": {k: len(v) for k, v in by_ministry.items()},
    }
    (OUT / "pdf_business_cards.json").write_text(json.dumps(all_cards, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "pdf_parse_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (ART / "pdf_parse_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("total_cards", len(all_cards))

if __name__ == "__main__":
    main()
