#!/usr/bin/env python3
"""Build a standalone HTML explorer from the enriched canonical tree.

The Open Fiscal ``ExpenditureBudgetAdd2`` hierarchy and amount remain the
canonical spine.  Matched ministry-PDF cards and LOFIN keyword candidates are
shown only as enrichment on detail-business leaves.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / "data" / "normalized" / "canonical_business_tree_2026_pilots.json"
SUMMARY = ROOT / "data" / "normalized" / "canonical_business_2026_pilots_summary.json"
OUT = ROOT / "artifacts" / "detail_business_structure.html"


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(
            f"missing canonical tree: {path}\n"
            "run `python3 code/build_canonical_dataset.py` first"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"expected a JSON object in {path}")
    return value


def infer_year(summary: dict) -> int:
    try:
        return int(summary.get("year"))
    except (TypeError, ValueError):
        match = re.search(r"(?:19|20)\d{2}", TREE.name)
        return int(match.group()) if match else 2026


def safe_json_for_html(value: object) -> str:
    """Serialize JSON without allowing an embedded value to close its tag."""

    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    # HTML end-tag matching is case-insensitive, so cover unusual mixed-case
    # strings too while retaining readable Korean JSON in the standalone file.
    return re.sub(r"</", lambda _match: "<\\/", serialized, flags=re.IGNORECASE)


HTML_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Koreabudget100 · 예산 세부사업 구조도</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #08111f;
      --panel: #101b2e;
      --panel-2: #0c1728;
      --line: #263754;
      --text: #edf3ff;
      --muted: #9eb0cc;
      --blue: #75aaff;
      --green: #7fdcb5;
      --yellow: #f3ce7b;
      --pink: #e9a6da;
      --orange: #ffad75;
      --red: #ff9a9a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      background:
        radial-gradient(1000px 520px at 0 -10%, #1b3159 0, transparent 70%),
        var(--bg);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
      line-height: 1.5;
    }
    code { color: #c9dcff; }
    header {
      position: sticky;
      top: 0;
      z-index: 10;
      padding: 18px max(18px, calc((100vw - 1500px) / 2));
      border-bottom: 1px solid var(--line);
      background: rgba(8, 17, 31, .92);
      backdrop-filter: blur(12px);
    }
    h1 { margin: 0 0 5px; font-size: 20px; }
    .sub { color: var(--muted); font-size: 13px; }
    .warning {
      margin-top: 10px;
      padding: 8px 10px;
      border: 1px solid #6d5233;
      border-radius: 9px;
      color: #ffe0ad;
      background: #2a2118;
      font-size: 12px;
    }
    .toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    input, select, button, .workflow-link {
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 9px;
      color: var(--text);
      background: var(--panel);
      font: inherit;
      font-size: 13px;
      padding: 7px 10px;
    }
    input { flex: 1 1 360px; min-width: 240px; }
    button { cursor: pointer; }
    .workflow-link { display: inline-flex; align-items: center; text-decoration: none; }
    button:hover, button:focus-visible, input:focus-visible, select:focus-visible,
    .workflow-link:hover, .workflow-link:focus-visible {
      border-color: var(--blue);
      outline: none;
    }
    main {
      max-width: 1500px;
      margin: 0 auto;
      padding: 16px 18px 50px;
    }
    .stats { display: grid; grid-template-columns: repeat(5, minmax(145px, 1fr)); gap: 9px; margin-bottom: 15px; }
    .stat { padding: 10px 12px; border: 1px solid var(--line); border-radius: 11px; background: var(--panel); }
    .stat span { display: block; color: var(--muted); font-size: 11px; }
    .stat b { display: block; margin-top: 2px; font-size: 16px; }
    details.node {
      margin: 7px 0;
      padding: 7px 9px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--panel);
    }
    details.node details.node { background: var(--panel-2); }
    summary {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      cursor: pointer;
      list-style: none;
    }
    summary::-webkit-details-marker { display: none; }
    summary::before { content: "▸"; width: 12px; color: var(--muted); flex: 0 0 auto; }
    details[open] > summary::before { content: "▾"; }
    .summary-name { flex: 1; font-weight: 600; overflow-wrap: anywhere; }
    .summary-meta { color: var(--muted); font-size: 12px; white-space: nowrap; }
    .lvl-ministry > summary .summary-name { color: #a9c9ff; }
    .lvl-account > summary .summary-name { color: #a7ebcf; }
    .lvl-program > summary .summary-name { color: #f5d693; }
    .lvl-unit > summary .summary-name { color: #edb6e1; }
    .lvl-detail > summary .summary-name { color: var(--text); font-weight: 520; }
    .children { margin-left: 13px; }
    .business-panel {
      margin: 9px 0 2px 24px;
      padding: 11px;
      border-left: 3px solid #385680;
      border-radius: 6px;
      background: #091321;
    }
    .section { margin-top: 13px; }
    .section:first-child { margin-top: 0; }
    .section-title { margin: 0 0 7px; color: #c9d8ef; font-size: 12px; font-weight: 700; letter-spacing: .02em; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip {
      display: inline-flex;
      gap: 5px;
      align-items: center;
      border: 1px solid #365070;
      border-radius: 999px;
      padding: 3px 8px;
      color: #d9e7fa;
      background: #12233a;
      font-size: 11px;
    }
    .chip.pdf { border-color: #725e33; background: #2a2417; color: #ffe1a4; }
    .chip.lofin { border-color: #426a59; background: #132a22; color: #aaf0d1; }
    .card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 7px; }
    .enrich-card { padding: 9px; border: 1px solid #263b59; border-radius: 8px; background: #0e1b2d; font-size: 12px; }
    .enrich-card strong { display: block; color: #f3d595; font-size: 13px; }
    .kv { display: grid; grid-template-columns: 86px 1fr; gap: 2px 7px; margin-top: 6px; }
    .kv dt { color: var(--muted); }
    .kv dd { margin: 0; overflow-wrap: anywhere; }
    .local-summary { border-color: #315c4d; }
    .local-warning { margin-top: 7px; color: #ffcf96; }
    .muted { color: var(--muted); }
    .empty { padding: 24px; color: var(--muted); text-align: center; }
    footer { max-width: 1500px; margin: 0 auto; padding: 0 18px 28px; color: var(--muted); font-size: 11px; }
    mark { color: inherit; background: #705b1c; }
    @media (max-width: 850px) {
      .stats { grid-template-columns: repeat(2, 1fr); }
      .summary-meta { white-space: normal; text-align: right; }
      .children { margin-left: 4px; }
      .business-panel { margin-left: 5px; }
    }
    @media print {
      header { position: static; }
      .toolbar { display: none; }
      body { background: white; color: black; }
      details.node, .stat, .business-panel, .enrich-card { background: white; color: black; border-color: #aaa; }
    }
  </style>
</head>
<body>
  <header>
    <h1>__YEAR__ 예산 세부사업 구조도 · 3개 부처 파일럿</h1>
    <div class="sub">
      기준: 열린재정 OpenAPI <code>ExpenditureBudgetAdd2</code> ·
      계층: 부처 → 회계 → 프로그램 → 단위사업 → 세부사업 ·
      금액: 국회확정액 <code>Y_YY_DFN_KCUR_AMT</code> ·
      PDF와 LOFIN QWGJK는 정규 사업에 붙인 보강 정보입니다.
    </div>
    <div class="warning">
      LOFIN 표시는 <code>keyword_candidate</code> 탐색 결과이며 중앙예산과 대사한 확정 매칭이 아닙니다.
      광역·기초 반영액이 같은 재원을 중복 표현할 수 있으므로 반영액 합계를 중앙예산 합계와 직접 비교하지 마세요.
    </div>
    <div class="toolbar">
      <input id="q" type="search" autocomplete="off" placeholder="사업명 · 집행기관 · 집행채널 · 지역명 검색" aria-label="구조도 검색" />
      <select id="depth" aria-label="펼칠 깊이">
        <option value="1">부처까지만</option>
        <option value="2">회계까지</option>
        <option value="3">프로그램까지</option>
        <option value="4" selected>단위사업까지</option>
        <option value="5">세부사업까지</option>
      </select>
      <button id="expand" type="button">깊이 적용</button>
      <button id="collapse" type="button">모두 접기</button>
      <a class="workflow-link" href="detailed_business_workflows.html">세부사업 업무 체계도 열기</a>
    </div>
  </header>
  <main>
    <div class="stats" id="stats" aria-live="polite"></div>
    <div id="tree"></div>
  </main>
  <footer>
    Koreabudget100 · API 키 미포함 · canonical tree: __TREE__ ·
    source of truth: ExpenditureBudgetAdd2 / Y_YY_DFN_KCUR_AMT
  </footer>

  <script id="tree-data" type="application/json">__PAYLOAD__</script>
  <script>
    'use strict';
    const PAYLOAD = JSON.parse(document.getElementById('tree-data').textContent);
    const ROOT = PAYLOAD.tree;
    const NODES = Array.isArray(ROOT.children) ? ROOT.children : [];
    const LEVELS = ['ministry', 'account', 'program', 'unit', 'detail'];
    const SEARCH_INDEX = new WeakMap();

    const number = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
    const text = (value, fallback = '-') => value == null || value === '' ? fallback : String(value);
    const won = (value) => Math.round(number(value)).toLocaleString('ko-KR') + '원';
    const compactWon = (value) => {
      const v = number(value);
      if (Math.abs(v) >= 1e12) return (v / 1e12).toFixed(2) + '조원';
      if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(2) + '억원';
      if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(1) + '만원';
      return won(v);
    };
    const percent = (value) => (number(value) * 100).toFixed(1) + '%';

    function el(tag, className, value) {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (value != null) node.textContent = value;
      return node;
    }

    function indexTerms(node) {
      const business = node.business || {};
      const terms = [node.name];
      (business.execution_channels || []).forEach((channel) => {
        terms.push(channel.code, channel.label);
      });
      (business.pdf_enrichment || []).forEach((pdf) => {
        terms.push(pdf.title, pdf.code_hint, pdf.implementer, pdf.source_pdf);
        (pdf.execution_paths || []).forEach((path) => terms.push(path));
      });
      const local = business.local_summary || {};
      terms.push(local.match_status, 'LOFIN', 'QWGJK');
      (local.top_local_govs || []).forEach((gov) => {
        terms.push(gov.name, gov.level);
      });
      (business.source_refs || []).forEach((ref) => {
        terms.push(ref.source, ref.path);
      });
      return terms.filter(Boolean).join(' ').normalize('NFKC').toLocaleLowerCase('ko-KR');
    }

    function buildSearchIndex(nodes) {
      nodes.forEach((node) => {
        SEARCH_INDEX.set(node, indexTerms(node));
        buildSearchIndex(node.children || []);
      });
    }

    function addKeyValues(parent, rows) {
      const dl = el('dl', 'kv');
      rows.forEach(([label, value]) => {
        if (value == null || value === '' || (Array.isArray(value) && !value.length)) return;
        dl.append(el('dt', '', label), el('dd', '', Array.isArray(value) ? value.join(' · ') : String(value)));
      });
      parent.appendChild(dl);
    }

    function renderChannels(panel, channels) {
      const section = el('section', 'section');
      section.appendChild(el('h3', 'section-title', '열린재정 비목 기반 집행채널'));
      const chips = el('div', 'chips');
      channels.forEach((channel) => {
        const detail = [
          text(channel.label, text(channel.code)),
          compactWon(channel.amount_won),
          percent(channel.share),
          `${number(channel.line_count).toLocaleString('ko-KR')}개 비목`,
        ].join(' · ');
        chips.appendChild(el('span', 'chip', detail));
      });
      section.appendChild(chips);
      panel.appendChild(section);
    }

    function renderPdfs(panel, pdfs) {
      const section = el('section', 'section');
      section.appendChild(el('h3', 'section-title', `부처 예산설명자료 PDF 보강 · 확정 매칭 ${pdfs.length}건`));
      const grid = el('div', 'card-grid');
      pdfs.forEach((pdf) => {
        const card = el('article', 'enrich-card');
        card.appendChild(el('strong', '', text(pdf.title, '제목 없음')));
        const pages = pdf.page_start == null
          ? null
          : pdf.page_end && pdf.page_end !== pdf.page_start
            ? `${pdf.page_start}–${pdf.page_end}쪽`
            : `${pdf.page_start}쪽`;
        addKeyValues(card, [
          ['사업 코드', pdf.code_hint],
          ['집행기관', pdf.implementer],
          ['사업 방식', pdf.execution_paths || []],
          ['출처', pdf.source_pdf],
          ['페이지', pages],
          ['매칭', [pdf.confidence, pdf.method, pdf.score == null ? null : `점수 ${pdf.score}`].filter(Boolean)],
        ]);
        grid.appendChild(card);
      });
      section.appendChild(grid);
      panel.appendChild(section);
    }

    function renderLocal(panel, local) {
      const section = el('section', 'section');
      section.appendChild(el('h3', 'section-title', 'LOFIN QWGJK 지역 반영 탐색'));
      const card = el('article', 'enrich-card local-summary');
      const chips = el('div', 'chips');
      chips.appendChild(el('span', 'chip lofin', text(local.match_status, 'keyword_candidate')));
      chips.appendChild(el('span', 'chip lofin', `${number(local.row_count).toLocaleString('ko-KR')}개 후보 행`));
      card.appendChild(chips);
      const levels = Object.entries(local.by_level || {}).map(([level, value]) =>
        `${level} ${number(value.row_count).toLocaleString('ko-KR')}건 / ${compactWon(value.national_amount_won)}`
      );
      const governments = (local.top_local_govs || []).slice(0, 10).map((gov) =>
        `${text(gov.name, '미상')} ${compactWon(gov.national_amount_won)}`
      );
      addKeyValues(card, [
        ['중앙 이전액', local.central_local_transfer_amount_won == null ? null : won(local.central_local_transfer_amount_won)],
        ['반영액 합계', local.national_reflection_sum_won == null ? null : won(local.national_reflection_sum_won)],
        ['단계별', levels],
        ['상위 지역', governments],
      ]);
      const warning = el(
        'div',
        'local-warning',
        text(local.sum_warning, '키워드 후보이며 광역·기초 반영액이 중복될 수 있어 중앙예산과 직접 대사하지 않습니다.')
      );
      card.appendChild(warning);
      section.appendChild(card);
      panel.appendChild(section);
    }

    function renderBusiness(node) {
      const business = node.business || {};
      const panel = el('div', 'business-panel');
      const idRow = el('div', 'chips');
      idRow.appendChild(el('span', 'chip', `정규 사업 ID ${text(business.id)}`));
      if ((business.pdf_enrichment || []).length) idRow.appendChild(el('span', 'chip pdf', 'PDF 보강'));
      if (business.local_summary) idRow.appendChild(el('span', 'chip lofin', 'LOFIN keyword_candidate'));
      panel.appendChild(idRow);
      if ((business.execution_channels || []).length) renderChannels(panel, business.execution_channels);
      if ((business.pdf_enrichment || []).length) renderPdfs(panel, business.pdf_enrichment);
      if (business.local_summary) renderLocal(panel, business.local_summary);
      return panel;
    }

    function renderNode(node, depth) {
      const level = LEVELS[Math.min(depth, LEVELS.length - 1)];
      const details = el('details', `node lvl-${level}`);
      details.dataset.depth = String(depth + 1);
      details.dataset.search = SEARCH_INDEX.get(node) || '';

      const summary = el('summary');
      summary.append(
        el('span', 'summary-name', text(node.name, '(이름 없음)')),
        el('span', 'summary-meta', `${compactWon(node.amount)} · n=${number(node.count || 1).toLocaleString('ko-KR')}`),
      );
      details.appendChild(summary);

      const children = node.children || [];
      if (children.length) {
        const box = el('div', 'children');
        children.forEach((child) => box.appendChild(renderNode(child, depth + 1)));
        details.appendChild(box);
      } else if (node.business) {
        details.appendChild(renderBusiness(node));
      }
      return details;
    }

    function collectStats(nodes) {
      const result = { nodes: 0, details: 0, pdfBusinesses: 0, localBusinesses: 0 };
      const walk = (node) => {
        result.nodes += 1;
        const children = node.children || [];
        if (!children.length) {
          result.details += 1;
          const business = node.business || {};
          if ((business.pdf_enrichment || []).length) result.pdfBusinesses += 1;
          if (business.local_summary) result.localBusinesses += 1;
        }
        children.forEach(walk);
      };
      nodes.forEach(walk);
      return result;
    }

    function renderStats() {
      const stats = collectStats(NODES);
      const cards = [
        ['부처', NODES.length.toLocaleString('ko-KR')],
        ['세부사업', stats.details.toLocaleString('ko-KR')],
        ['국회확정 합계', compactWon(ROOT.amount)],
        ['PDF 보강 사업', stats.pdfBusinesses.toLocaleString('ko-KR')],
        ['LOFIN 후보 사업', stats.localBusinesses.toLocaleString('ko-KR')],
      ];
      const box = document.getElementById('stats');
      cards.forEach(([label, value]) => {
        const card = el('div', 'stat');
        card.append(el('span', '', label), el('b', '', value));
        box.appendChild(card);
      });
    }

    function applyDepth(maxDepth) {
      document.querySelectorAll('#tree details.node').forEach((node) => {
        node.open = number(node.dataset.depth) < maxDepth;
      });
    }

    function showBranch(node) {
      node.style.display = '';
      node.open = true;
      node.querySelectorAll(':scope > .children details.node').forEach((child) => {
        child.style.display = '';
      });
      let parent = node.parentElement;
      while (parent && parent.id !== 'tree') {
        if (parent.matches('details.node')) {
          parent.style.display = '';
          parent.open = true;
        }
        parent = parent.parentElement;
      }
    }

    function filter(query) {
      const q = text(query, '').trim().normalize('NFKC').toLocaleLowerCase('ko-KR');
      const nodes = [...document.querySelectorAll('#tree details.node')];
      nodes.forEach((node) => { node.style.display = q ? 'none' : ''; });
      if (!q) {
        applyDepth(number(document.getElementById('depth').value));
        return;
      }
      nodes.filter((node) => (node.dataset.search || '').includes(q)).forEach(showBranch);
    }

    buildSearchIndex(NODES);
    renderStats();
    const treeBox = document.getElementById('tree');
    if (NODES.length) NODES.forEach((node) => treeBox.appendChild(renderNode(node, 0)));
    else treeBox.appendChild(el('div', 'empty', '표시할 정규 사업 트리가 없습니다.'));
    applyDepth(4);

    document.getElementById('expand').addEventListener('click', () => {
      document.getElementById('q').value = '';
      filter('');
    });
    document.getElementById('collapse').addEventListener('click', () => applyDepth(0));
    document.getElementById('q').addEventListener('input', (event) => filter(event.target.value));
  </script>
</body>
</html>
"""


def build_html(tree: dict, summary: dict, year: int) -> str:
    payload = {
        "meta": {
            "year": year,
            "tree_file": TREE.name,
            "source": "ExpenditureBudgetAdd2",
            "amount_field": "Y_YY_DFN_KCUR_AMT",
            "summary": summary,
        },
        "tree": tree,
    }
    return (
        HTML_TEMPLATE.replace("__PAYLOAD__", safe_json_for_html(payload))
        .replace("__YEAR__", str(year))
        .replace("__TREE__", html.escape(TREE.name))
    )


def main() -> int:
    tree = load_json(TREE)
    if not isinstance(tree.get("children"), list):
        raise SystemExit(f"canonical tree has no children list: {TREE}")
    summary = load_json(SUMMARY) if SUMMARY.exists() else {}
    year = infer_year(summary)
    document = build_html(tree, summary, year)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(document, encoding="utf-8")
    year_out = OUT.with_name(f"detail_business_structure_{year}.html")
    year_out.write_text(document, encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"wrote {year_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
