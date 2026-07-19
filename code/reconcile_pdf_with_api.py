#!/usr/bin/env python3
"""Reconcile noisy PDF business cards onto Open Fiscal detail businesses."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NORM = ROOT / "data" / "normalized"
ART = ROOT / "artifacts"

NOISE_TITLE_RE = re.compile(
    r"(본예산|추경|요구안|증감|결산|구분|피보조|피출연|지원\s*금액|보조율|"
    r"법적근거|단위:|백만원|억원|colspan|rowspan|</|소관부처\s*)"
)
HTML_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^\w가-힣]+", re.UNICODE)
CODE_RE = re.compile(r"(\d{3,6})\s*[-–]\s*(\d{2,6})")
HEADER_TITLE_RE = re.compile(
    r"[\(（]\s*\d{1,3}\s*[\)）]\s*([가-힣A-Za-z0-9()·\s/\-]{4,80}?)\s*"
    r"[\(（]\s*\d{3,6}\s*[-–]\s*\d{2,6}\s*[\)）]"
)
BIZNAME_RE = re.compile(r"사\s*업\s*명\s*[:：]?\s*([가-힣A-Za-z0-9()·\s/\-]{4,80})")
IMPL_RE = re.compile(r"사업시행주체\s*[:：]?\s*([가-힣A-Za-z0-9,·\s]{2,80})")
LEADING_NUM_RE = re.compile(r"^[\(（]?\s*\d{1,3}\s*[\)）]\s*")
TRAILING_CODE_RE = re.compile(r"[\(（]\s*\d{3,6}\s*[-–]\s*\d{2,6}\s*[\)）]\s*$")
OFFICE_SPLIT_RE = re.compile(r"\s*소관부처\s*")
TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")

STOP_TOKENS = {
    "위한", "및", "등", "관련", "사업", "지원", "추진", "관리", "운영", "기본",
    "경비", "인건비", "소관", "부처", "실국", "기관", "계정", "분야", "부문",
    "일반", "회계",
}

IMPLEMENTER_PLACEHOLDERS = {
    "-",
    "기관명",
    "구분",
    "명칭",
    "미정",
    "사업",
    "사업명",
    "사업시행주체",
    "시행주체",
    "소관부처",
    "직접수행",
    "직접 수행",
    "지자체 보조",
    "해당없음",
    "해당 없음",
    "절차내용",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def norm_text(s):
    if not s:
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    t = HTML_RE.sub(" ", t)
    t = t.replace("·", "").replace("ㆍ", "").replace("‧", "")
    t = t.replace("（", "(").replace("）", ")")
    t = SPACE_RE.sub("", t)
    t = PUNCT_RE.sub("", t)
    return t.lower()


def tokens(s):
    raw = unicodedata.normalize("NFKC", str(s or ""))
    raw = HTML_RE.sub(" ", raw)
    raw = re.sub(r"[()\[\]{}|/\\]", " ", raw)
    out = set()
    for p in TOKEN_RE.findall(raw):
        p2 = p.lower()
        if p2 in STOP_TOKENS or p2.isdigit():
            continue
        out.add(p2)
    compact = norm_text(s)
    if len(compact) >= 4:
        out.add(compact)
    return out


def clean_pdf_title(card):
    # Kordoc cards are created only from a structurally validated, coded
    # heading.  Do not apply the broad legacy text-noise filter to those
    # titles: valid names can contain words such as ``결산`` or ``기구``.
    if card.get("extractor") == "kordoc_chunks" and card.get("title"):
        structured = HTML_RE.sub(" ", str(card["title"]))
        structured = SPACE_RE.sub(" ", structured).strip(" :-·.|")
        if (
            2 <= len(structured) <= 120
            and "|" not in structured
            and "</" not in structured
            and structured not in {"사업명", "사업개요", "구분", "코드", "명칭"}
        ):
            return structured
    cands = []
    title = card.get("title") or ""
    cands.append(title)
    fields = card.get("fields") or {}
    if fields.get("사업명"):
        cands.append(fields["사업명"])
    snippet = card.get("snippet") or ""
    m = HEADER_TITLE_RE.search(snippet)
    if m:
        cands.insert(0, m.group(1))
    m2 = BIZNAME_RE.search(snippet)
    if m2:
        cands.append(m2.group(1))
    best = None
    for c in cands:
        t = HTML_RE.sub(" ", c or "")
        t = SPACE_RE.sub(" ", t).strip(" :-·.|")
        t = LEADING_NUM_RE.sub("", t).strip()
        t = TRAILING_CODE_RE.sub("", t).strip()
        t = OFFICE_SPLIT_RE.split(t)[0].strip()
        if len(t) < 4 or len(t) > 80:
            continue
        if NOISE_TITLE_RE.search(t):
            continue
        if "|" in t and t.count("|") >= 2:
            continue
        if best is None:
            best = t
        elif len(best) > 40 and len(t) <= 40:
            best = t
        elif abs(len(t) - 12) < abs(len(best) - 12) and len(t) <= 40:
            best = t
    return best


def extract_code(card):
    fields = card.get("fields") or {}
    for key in ("세부사업코드", "사업코드", "코드"):
        val = fields.get(key)
        if not val:
            continue
        normalized = unicodedata.normalize("NFKC", str(val))
        normalized = (
            normalized.replace("–", "-")
            .replace("～", "~")
            .replace("\\~", "~")
        )
        normalized = re.sub(r"\s+", "", normalized)
        if re.fullmatch(r"\d{3,6}-\d{2,6}(?:[~,]\d{2,6})*", normalized):
            return normalized
        m = CODE_RE.search(str(val))
        if m:
            return m.group(1) + "-" + m.group(2)
    blob = " ".join([
        str(card.get("title") or ""),
        str(card.get("snippet") or ""),
        json.dumps(fields, ensure_ascii=False),
    ])
    m = CODE_RE.search(blob)
    if m:
        return m.group(1) + "-" + m.group(2)
    return None


def extract_implementer(card):
    fields = card.get("fields") or {}
    for key in ("사업시행주체", "시행주체", "추진체계"):
        val = fields.get(key)
        if not val:
            continue
        t = HTML_RE.sub(" ", str(val))
        t = SPACE_RE.sub(" ", t).strip()
        if len(t) < 2:
            continue
        if t in IMPLEMENTER_PLACEHOLDERS:
            continue
        if (
            "</" in t
            or "최근 4년간" in t
            or "최근 5년" in t
            or "결산" in t
            or "공통요구자료" in t
        ):
            continue
        return t[:200]
    sn = card.get("snippet") or ""
    m = IMPL_RE.search(sn)
    if m:
        value = SPACE_RE.sub(" ", m.group(1)).strip()[:200]
        if value not in IMPLEMENTER_PLACEHOLDERS:
            return value
    return None


def bigrams(s):
    if len(s) < 2:
        return set()
    return {s[i : i + 2] for i in range(len(s) - 1)}


def score_pair(pdf_title, api_name, pdf_tokens, api_tokens):
    pn = norm_text(pdf_title)
    an = norm_text(api_name)
    if not pn or not an:
        return 0.0, "none"
    if pn == an:
        return 100.0, "exact_norm"
    if pn in an or an in pn:
        ratio = min(len(pn), len(an)) / max(len(pn), len(an))
        return 80.0 + 15.0 * ratio, "contains_norm"
    inter = pdf_tokens & api_tokens
    inter = {x for x in inter if x != pn and x != an}
    if not inter:
        b_i = bigrams(pn) & bigrams(an)
        if not b_i:
            return 0.0, "none"
        j = len(b_i) / max(1, len(bigrams(pn) | bigrams(an)))
        if j < 0.35:
            return 0.0, "none"
        return 40.0 + 40.0 * j, "char_bigram"
    j = len(inter) / max(1, len(pdf_tokens | api_tokens))
    bonus = min(20.0, 5.0 * max(0, len(inter) - 1))
    score = 45.0 + 45.0 * j + bonus
    return min(score, 95.0), "token_overlap"


def build_api_index(details):
    by_office = defaultdict(list)
    for d in details:
        office = d.get("office_name") or ""
        name = d.get("detail_business_name") or ""
        item = {
            "office_name": office,
            "detail_business_name": name,
            "norm": norm_text(name),
            "tokens": tokens(name),
            "program_name": d.get("program_name"),
            "unit_business_name": d.get("unit_business_name"),
            "account_name": d.get("account_name"),
            "field_name": d.get("field_name"),
            "section_name": d.get("section_name"),
            "congress_amt": d.get("congress_amt"),
            "year": d.get("year"),
        }
        by_office[office].append(item)
    return by_office


def match_card(card, api_by_office):
    ministry = card.get("ministry") or ""
    cleaned = clean_pdf_title(card)
    if not cleaned:
        raw = (card.get("title") or "").strip()
        # last-resort lightweight clean
        raw = OFFICE_SPLIT_RE.split(raw)[0].strip()
        if len(raw) >= 4 and not NOISE_TITLE_RE.search(raw):
            cleaned = raw
    code = extract_code(card)
    fields = card.get("fields") or {}
    code_type = fields.get("코드유형") or (
        "aggregate" if code and re.search(r"[~,]", code) else "detail"
    )
    implementer = extract_implementer(card)
    exec_paths = card.get("exec_paths") or []
    pdf_tokens = tokens(cleaned) if cleaned else set()
    candidates = list(api_by_office.get(ministry, []))
    ranked = []
    for api in candidates:
        sc, reason = score_pair(
            cleaned or "",
            api["detail_business_name"],
            pdf_tokens,
            api["tokens"],
        )
        if implementer and 0 < sc < 88:
            impl_n = norm_text(implementer)
            api_n = api["norm"]
            impl_tokens = [tok for tok in tokens(implementer) if len(tok) >= 3]
            boosted = False
            if impl_n and impl_n in api_n:
                boosted = True
            elif any(tok in api_n for tok in impl_tokens):
                boosted = True
            if boosted:
                sc += 8.0
                reason = reason + "+implementer"
        sc = min(sc, 100.0)
        if sc <= 0:
            continue
        ranked.append((sc, reason, api))
    ranked.sort(key=lambda x: x[0], reverse=True)
    best = ranked[0] if ranked else None
    second = ranked[1] if len(ranked) > 1 else None
    status = "unmatched"
    conf = "none"
    match = None
    method = "none"
    margin = (best[0] - second[0]) if best and second else None
    exact_best = bool(best and best[1].startswith("exact_norm"))
    exact_tie = bool(exact_best and second and second[1].startswith("exact_norm"))
    if code_type == "aggregate":
        # A range/list heading is a roll-up over several detail businesses.
        # Keep it as unresolved evidence instead of attaching it to an
        # arbitrary single API row.
        status = "ambiguous"
        conf = "low"
        method = "aggregate_heading"
    elif exact_best and not exact_tie:
        status = "matched"
        conf = "high"
        match = best[2]
        method = best[1]
    elif best and best[0] >= 88 and (margin is None or margin >= 8):
        status = "matched"
        conf = "high"
        match = best[2]
        method = best[1]
    elif best and best[0] >= 70:
        if second is None or (best[0] - second[0]) >= 8:
            status = "matched"
            conf = "medium"
            match = best[2]
            method = best[1]
        else:
            status = "ambiguous"
            conf = "low"
            method = best[1]
    elif best and best[0] >= 55:
        status = "ambiguous"
        conf = "low"
        method = best[1]
    top3 = []
    for sc, reason, api in ranked[:3]:
        top3.append({
            "score": round(sc, 2),
            "reason": reason,
            "office_name": api["office_name"],
            "detail_business_name": api["detail_business_name"],
            "congress_amt": api["congress_amt"],
        })
    api_match = None
    if match is not None:
        api_match = {
            "office_name": match["office_name"],
            "detail_business_name": match["detail_business_name"],
            "program_name": match["program_name"],
            "unit_business_name": match["unit_business_name"],
            "account_name": match["account_name"],
            "field_name": match["field_name"],
            "section_name": match["section_name"],
            "congress_amt": match["congress_amt"],
            "year": match["year"],
        }
    return {
        "pdf": {
            "ministry": ministry,
            "raw_title": card.get("title"),
            "clean_title": cleaned,
            "code_hint": code,
            "code_type": code_type,
            "implementer": implementer,
            "exec_paths": exec_paths,
            "extractor": card.get("extractor"),
            "source_pdf": card.get("source_pdf"),
            "page_start": card.get("page_start"),
            "page_end": card.get("page_end"),
            "anchor_chunk_id": card.get("anchor_chunk_id"),
            "anchor_chunk_ids": card.get("anchor_chunk_ids") or [],
            "source_chunk_start": card.get("source_chunk_start"),
            "source_chunk_end": card.get("source_chunk_end"),
            "snippet": (card.get("snippet") or "")[:280],
        },
        "status": status,
        "confidence": conf,
        "method": method,
        "score": round(best[0], 2) if best else 0.0,
        "api_match": api_match,
        "top3": top3,
        "enrichment": {
            "canonical_name": match["detail_business_name"] if match else cleaned,
            "canonical_amount": match["congress_amt"] if match else None,
            "pdf_exec_paths": exec_paths,
            "pdf_implementer": implementer,
            "pdf_code_hint": code,
            "pdf_code_type": code_type,
            "amount_source": "openfiscal" if match else None,
            "name_source": "openfiscal" if match and status == "matched" else "pdf_clean",
        },
    }


def attach_lofin_offline(rows, lofin_rows):
    for r in rows:
        match = r.get("api_match")
        exact_rows = []
        legacy_rows = []
        target_key = None
        if match:
            target_key = (
                str(match.get("year") or ""),
                str(match.get("office_name") or ""),
                str(match.get("account_name") or ""),
                str(match.get("program_name") or ""),
                str(match.get("unit_business_name") or ""),
                str(match.get("detail_business_name") or ""),
            )
        for lr in lofin_rows:
            central_key = lr.get("central_business_key")
            if central_key is not None:
                if (
                    target_key is not None
                    and isinstance(central_key, (list, tuple))
                    and len(central_key) == 6
                    and tuple(str(value or "").strip() for value in central_key) == target_key
                ):
                    exact_rows.append(lr)
                # Keyed candidates belong only to their declared central row.
                continue
            legacy_rows.append(lr)

        candidate_rows = exact_rows
        attachment_method = "exact_central_business_key"
        if not candidate_rows and legacy_rows:
            attachment_method = "legacy_keyword_fallback"
            keys = []
            if match:
                keys.append(match["detail_business_name"])
            if r["pdf"].get("clean_title"):
                keys.append(r["pdf"]["clean_title"])
            candidate_rows = []
            for key in keys:
                kn = norm_text(key)
                if len(kn) < 4:
                    continue
                ktoks = sorted(t for t in tokens(key) if len(t) >= 3)[:4]
                for lr in legacy_rows:
                    ln = lr.get("detail_business_name") or ""
                    lnn = norm_text(ln)
                    ok = bool(kn and (kn in lnn or lnn in kn))
                    if not ok and ktoks:
                        need = max(1, min(2, len(ktoks)))
                        ok = sum(1 for t in ktoks if t in lnn) >= need
                    if ok:
                        candidate_rows.append(lr)

        hits = []
        for lr in candidate_rows:
            try:
                national_amount = float(
                    str(lr.get("national_amt") or 0).replace(",", "")
                )
            except (TypeError, ValueError):
                continue
            if national_amount <= 0:
                continue
            ln = lr.get("detail_business_name") or ""
            hits.append({
                "local_gov_code": lr.get("local_gov_code"),
                "local_gov_name": lr.get("local_gov_name"),
                "local_level": lr.get("local_level"),
                "detail_business_name": ln,
                "detail_business_code": lr.get("detail_business_code"),
                "national_amt": lr.get("national_amt"),
                "keyword": lr.get("keyword"),
                "keyword_strategy": lr.get("keyword_strategy"),
                "match_status": lr.get("match_status") or "keyword_candidate",
                "attachment_method": attachment_method,
                "central_business_key": lr.get("central_business_key"),
                "year": lr.get("year"),
                "exe_ymd": lr.get("exe_ymd"),
            })
        uniq = []
        seen = set()
        for h in hits:
            k = (
                h.get("exe_ymd"),
                h.get("local_gov_code"),
                h.get("detail_business_code"),
            )
            if k in seen:
                continue
            seen.add(k)
            uniq.append(h)
        r["lofin_reflections"] = uniq
        r["lofin_hit_count"] = len(uniq)


def summarize(rows):
    c = Counter(r["status"] for r in rows)
    conf = Counter(r["confidence"] for r in rows)
    methods = Counter(r["method"] for r in rows if r["status"] != "unmatched")
    matched_names = []
    for r in rows:
        matched_names.append({
            "pdf": r["pdf"].get("clean_title") or r["pdf"].get("raw_title"),
            "api": r["api_match"]["detail_business_name"] if r.get("api_match") else None,
            "score": r["score"],
            "status": r["status"],
            "method": r["method"],
            "exec_paths": r["pdf"].get("exec_paths"),
            "lofin_hits": r.get("lofin_hit_count", 0),
        })
    total = max(1, len(rows))
    return {
        "total_pdf_cards": len(rows),
        "status_counts": dict(c),
        "confidence_counts": dict(conf),
        "method_counts": dict(methods),
        "match_rate_matched_only": round(c.get("matched", 0) / total, 3),
        "match_rate_incl_ambiguous": round((c.get("matched", 0) + c.get("ambiguous", 0)) / total, 3),
        "rows_brief": matched_names,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-cards", default=str(NORM / "pdf_business_cards_pilot_samples.json"))
    ap.add_argument("--api-details", default=str(NORM / "expbudgetadd2_2026_pilots_details.json"))
    ap.add_argument("--lofin", default=str(NORM / "lofin_qwgjk_keyword_matches.json"))
    ap.add_argument("--tag", default="pilot_samples")
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="print aggregate results without listing every PDF/API pair",
    )
    args = ap.parse_args()
    pdf_cards = load_json(Path(args.pdf_cards))
    api_details = load_json(Path(args.api_details))
    lofin_path = Path(args.lofin)
    lofin_rows = load_json(lofin_path) if lofin_path.exists() else []
    api_by_office = build_api_index(api_details)
    rows = [match_card(card, api_by_office) for card in pdf_cards]
    attach_lofin_offline(rows, lofin_rows)
    summary = summarize(rows)
    summary["api_detail_count"] = len(api_details)
    summary["lofin_seed_count"] = len(lofin_rows)
    summary["tag"] = args.tag
    NORM.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)
    out_rows = NORM / ("reconcile_pdf_api_" + args.tag + ".json")
    out_sum = NORM / ("reconcile_pdf_api_" + args.tag + "_summary.json")
    out_rows.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    out_sum.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (ART / ("reconcile_pdf_api_" + args.tag + "_summary.json")).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("tag", args.tag)
    print("pdf_cards", len(pdf_cards), "api_details", len(api_details))
    print("status", summary["status_counts"])
    print("confidence", summary["confidence_counts"])
    print("match_rate_matched_only", summary["match_rate_matched_only"])
    print("match_rate_incl_ambiguous", summary["match_rate_incl_ambiguous"])
    if not args.quiet:
        print("--- pairs ---")
        for b in summary["rows_brief"]:
            print(
                "[{status:9}] {score:5.1f} | PDF: {pdf} | API: {api} | {method} | lofin={lofin}".format(
                    status=b["status"],
                    score=b["score"],
                    pdf=b["pdf"],
                    api=b["api"],
                    method=b["method"],
                    lofin=b["lofin_hits"],
                )
            )
    print("wrote", out_rows)
    print("wrote", out_sum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
