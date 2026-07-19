#!/usr/bin/env python3
"""Score pdftotext / kordoc / OpenDataLoader outputs on sample budget PDFs."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AB = ROOT / "data" / "parser_ab"
REPORT = AB / "reports" / "ab_score.json"

SAMPLES = ["mois_p798-812", "molit_p148-162"]

SIGNAL_PATTERNS = {
    "biz_name_header": r"사\s*업\s*명",
    "code_block": r"사업\s*코드\s*정보|세부사업",
    "support_form": r"지원형태|보조율|국고보조",
    "implementer": r"시행주체|수행주체|보조사업자",
    "budget_table": r"예산\s*(총괄|내역|현황)|기능별.*예산|산출\s*근거",
    "exec_path": r"직접\s*(수행|사업)|민간\s*보조|자치단체\s*보조|위탁|출연|융자|출자",
    "amount": r"\d{1,3}(?:,\d{3}){1,4}",
    "million_won": r"백만원|천원",
    "checkbox_style": r"[□■○●]",
    "md_table_row": r"^\s*\|.+\|\s*$",
}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return path.read_bytes().decode("utf-8", errors="replace")


def count_patterns(text: str) -> dict:
    out = {}
    for k, pat in SIGNAL_PATTERNS.items():
        flags = re.M if k == "md_table_row" else 0
        out[k] = len(re.findall(pat, text, flags))
    return out


def extract_biz_titles(text: str) -> list[str]:
    titles = []
    # common forms: 사 업 명 (n) title (code)
    for m in re.finditer(
        r"사\s*업\s*명\s*[\(（]?\s*\d*\s*[\)）]?\s*(.+?)(?:\n|$)",
        text,
    ):
        t = re.sub(r"\s+", " ", m.group(1)).strip(" :-·.")
        t = re.sub(r"[\(（]\s*\d{3,8}[-–]\d{2,6}\s*[\)）]\s*$", "", t).strip()
        if 4 <= len(t) <= 80 and not t.startswith("코드"):
            titles.append(t)
    # kordoc/markdown headings near business blocks
    for m in re.finditer(r"^#+\s*(.+)$", text, re.M):
        t = m.group(1).strip()
        if any(k in t for k in ("사업", "인건비", "조사", "지원", "관리")) and 4 <= len(t) <= 80:
            titles.append(t)
    # unique preserve order
    seen = set()
    uniq = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq[:20]


def score_one(text: str) -> dict:
    c = count_patterns(text)
    titles = extract_biz_titles(text)
    # heuristic quality score
    score = (
        c["biz_name_header"] * 5
        + c["code_block"] * 3
        + c["support_form"] * 3
        + c["implementer"] * 3
        + c["budget_table"] * 2
        + min(c["exec_path"], 30)
        + min(c["amount"], 50) * 0.2
        + c["million_won"] * 0.5
        + min(c["checkbox_style"], 40) * 0.3
        + min(c["md_table_row"], 80) * 0.4
        + len(titles) * 4
    )
    return {
        "chars": len(text),
        "lines": text.count("\n") + (1 if text else 0),
        "signals": c,
        "biz_titles_sample": titles,
        "biz_title_count": len(titles),
        "score": round(score, 2),
    }


def load_outputs(sample: str) -> dict:
    paths = {
        "pdftotext": AB / "pdftotext" / f"{sample}.txt",
        "kordoc_md": AB / "kordoc" / f"{sample}.md",
        "kordoc_chunks": AB / "kordoc" / f"{sample}.chunks.json",
        "odl_md": None,
        "odl_text": None,
        "odl_json": None,
    }
    # OpenDataLoader output names can vary; search
    odl_dir = AB / "odl"
    if odl_dir.exists():
        for p in odl_dir.rglob("*"):
            if not p.is_file():
                continue
            name = p.name.lower()
            if sample.lower() in name or sample.split("_")[0] in name:
                if name.endswith(".md") or "markdown" in name:
                    paths["odl_md"] = p
                elif name.endswith(".txt") or name.endswith(".text"):
                    paths["odl_text"] = p
                elif name.endswith(".json"):
                    paths["odl_json"] = p
        # fallback: any md/txt in odl if only one sample processed at a time
        if paths["odl_md"] is None:
            mds = list(odl_dir.glob("*.md")) + list(odl_dir.glob("**/*.md"))
            # prefer filename containing stem tokens
            for p in mds:
                if "mois" in sample and "mois" in p.name:
                    paths["odl_md"] = p
                if "molit" in sample and "molit" in p.name:
                    paths["odl_md"] = p
        if paths["odl_text"] is None:
            for p in list(odl_dir.glob("*.txt")) + list(odl_dir.glob("**/*.txt")):
                if "mois" in sample and "mois" in p.name:
                    paths["odl_text"] = p
                if "molit" in sample and "molit" in p.name:
                    paths["odl_text"] = p
        if paths["odl_json"] is None:
            for p in list(odl_dir.glob("*.json")) + list(odl_dir.glob("**/*.json")):
                if p.name.endswith(".time"):
                    continue
                if "mois" in sample and "mois" in p.name:
                    paths["odl_json"] = p
                if "molit" in sample and "molit" in p.name:
                    paths["odl_json"] = p

    out = {}
    for k, p in paths.items():
        if p is None:
            out[k] = {"path": None, "missing": True}
            continue
        if k == "kordoc_chunks":
            raw = read_text(p)
            # score both raw json string and joined text fields
            joined = raw
            try:
                data = json.loads(raw)
                parts = []
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            for key in ("text", "content", "markdown", "heading", "title"):
                                if item.get(key):
                                    parts.append(str(item[key]))
                            if item.get("breadcrumb"):
                                parts.append(" > ".join(map(str, item["breadcrumb"])) if isinstance(item["breadcrumb"], list) else str(item["breadcrumb"]))
                        else:
                            parts.append(str(item))
                elif isinstance(data, dict):
                    parts.append(json.dumps(data, ensure_ascii=False))
                joined = "\n".join(parts) if parts else raw
            except Exception:
                joined = raw
            sc = score_one(joined)
            sc["path"] = str(p)
            sc["missing"] = False
            sc["chunk_bytes"] = p.stat().st_size
            out[k] = sc
        else:
            text = read_text(p)
            sc = score_one(text)
            sc["path"] = str(p)
            sc["missing"] = False
            out[k] = sc
    return out


def read_time(path: Path) -> float | None:
    if not path.exists():
        return None
    t = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"real\s+([0-9.]+)", t)
    return float(m.group(1)) if m else None


def main() -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    result = {"samples": {}, "ranking_note": "Higher score = more recoverable business-structure signals"}
    totals = {"pdftotext": 0.0, "kordoc_md": 0.0, "kordoc_chunks": 0.0, "odl_md": 0.0, "odl_text": 0.0}

    for sample in SAMPLES:
        outs = load_outputs(sample)
        times = {
            "pdftotext": read_time(AB / "pdftotext" / f"{sample}.time"),
            "kordoc_md": read_time(AB / "kordoc" / f"{sample}.md.time"),
            "kordoc_chunks": read_time(AB / "kordoc" / f"{sample}.chunks.time"),
            "odl": read_time(AB / "odl" / f"{sample}.time"),
        }
        for k in totals:
            if not outs.get(k, {}).get("missing", True):
                totals[k] += outs[k].get("score", 0)
        # qualitative snips
        snips = {}
        for k, pkey in [
            ("pdftotext", AB / "pdftotext" / f"{sample}.txt"),
            ("kordoc_md", AB / "kordoc" / f"{sample}.md"),
        ]:
            txt = read_text(pkey)
            # find first business name vicinity
            m = re.search(r"사\s*업\s*명[\s\S]{0,400}", txt)
            snips[k] = re.sub(r"\s+", " ", m.group(0))[:300] if m else txt[:200]
        # odl snip if any
        odl_path = outs.get("odl_md", {}).get("path") or outs.get("odl_text", {}).get("path")
        if odl_path:
            txt = read_text(Path(odl_path))
            m = re.search(r"사\s*업\s*명[\s\S]{0,400}", txt)
            snips["odl"] = re.sub(r"\s+", " ", m.group(0))[:300] if m else txt[:200]
        else:
            snips["odl"] = None

        result["samples"][sample] = {"outputs": outs, "times_sec": times, "snips": snips}

    ranked = sorted(totals.items(), key=lambda x: -x[1])
    result["total_scores"] = totals
    result["ranking"] = [k for k, _ in ranked]
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total_scores": totals, "ranking": result["ranking"]}, ensure_ascii=False, indent=2))
    for sample, block in result["samples"].items():
        print("\n==", sample)
        for k, v in block["outputs"].items():
            if v.get("missing"):
                print(f"  {k}: MISSING")
            else:
                print(
                    f"  {k}: score={v['score']} titles={v['biz_title_count']} "
                    f"tables={v['signals'].get('md_table_row',0)} exec={v['signals'].get('exec_path',0)} chars={v['chars']}"
                )
        print("  times", block["times_sec"])
        for k, s in block["snips"].items():
            print(f"  snip[{k}]: {s}")


if __name__ == "__main__":
    main()
