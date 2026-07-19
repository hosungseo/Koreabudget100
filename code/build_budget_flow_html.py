#!/usr/bin/env python3
"""Build the standalone, interactive budget-flow map website."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "normalized" / "budget_flow_maps_2026_pilots.json"
OUT = ROOT / "artifacts" / "budget_flow_map.html"
OUT_YEAR = ROOT / "artifacts" / "budget_flow_map_2026.html"


def load_payload(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(
            f"missing budget-flow dataset: {path}\n"
            "run `python3 code/build_budget_flow_maps.py` first"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid budget-flow JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"expected a JSON object in {path}")
    maps = value.get("maps")
    if not isinstance(maps, list) or not maps:
        raise SystemExit(f"budget-flow dataset has no maps: {path}")
    return value


def safe_json_for_html(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


HTML_TEMPLATE = r'''<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="light dark" />
  <meta name="description" content="2026년 중앙 세부사업의 확정재원부터 지방자치단체의 예산현액·재원구성·지출 스냅샷까지 연결한 예산체계도" />
  <title>Koreabudget100 · __YEAR__ 예산체계도</title>
  <style>
    :root {
      color-scheme: light dark;
      --page: #f3f6f2;
      --surface: #ffffff;
      --surface-soft: #f7f9f6;
      --surface-strong: #eaf0eb;
      --ink: #17231e;
      --muted: #5c6b64;
      --faint: #86938d;
      --line: #cbd5ce;
      --line-strong: #99aaa0;
      --header: #071e15;
      --header-2: #0b2a1e;
      --header-ink: #f5fff9;
      --header-muted: #a8c6b7;
      --brand: #0a7b55;
      --brand-strong: #075b40;
      --brand-soft: #dff2e9;
      --blue: #3b6eaf;
      --blue-soft: #e7eef8;
      --brown: #9b6c4f;
      --brown-soft: #f3e9e1;
      --violet: #765f9e;
      --violet-soft: #eee9f6;
      --amber: #9b6816;
      --amber-soft: #faedcf;
      --danger: #a24a3e;
      --danger-soft: #f8e7e3;
      --shadow: 0 7px 20px rgba(20, 49, 37, .09);
      --edge-flow: #466157;
      --edge-class: #147e72;
      --edge-cross: #9b6c4f;
      --edge-candidate: #3b6eaf;
      --edge-context: #765f9e;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --page: #07100c;
        --surface: #101b16;
        --surface-soft: #14231c;
        --surface-strong: #1a3026;
        --ink: #eef7f2;
        --muted: #aabbb2;
        --faint: #83988e;
        --line: #30483d;
        --line-strong: #587065;
        --header: #03130d;
        --header-2: #082419;
        --brand-soft: #153a2b;
        --blue-soft: #172b44;
        --brown-soft: #33261e;
        --violet-soft: #2b2438;
        --amber-soft: #372c16;
        --danger-soft: #3b211e;
        --shadow: 0 8px 22px rgba(0, 0, 0, .28);
      }
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--page);
      font-family: Pretendard, "Noto Sans KR", -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
      line-height: 1.48;
    }
    button, input { font: inherit; }
    button, a { -webkit-tap-highlight-color: transparent; }
    button:focus-visible, input:focus-visible, a:focus-visible,
    .map-scroll:focus-visible {
      outline: 3px solid #5aa9ff;
      outline-offset: 2px;
    }
    a { color: inherit; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .skip-link {
      position: absolute;
      z-index: 100;
      top: 8px;
      left: 8px;
      transform: translateY(-160%);
      padding: 8px 12px;
      color: var(--header-ink);
      background: var(--brand-strong);
    }
    .skip-link:focus { transform: none; }
    .hero {
      color: var(--header-ink);
      background:
        radial-gradient(900px 380px at 95% -20%, rgba(37, 174, 117, .29), transparent 70%),
        linear-gradient(135deg, var(--header), var(--header-2));
      border-top: 7px solid #20a774;
    }
    .hero-inner {
      max-width: 1740px;
      margin: 0 auto;
      padding: 17px 24px 21px;
    }
    .hero-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      color: var(--header-muted);
      font-size: 12px;
    }
    .brand { color: var(--header-ink); font-weight: 800; letter-spacing: -.02em; }
    .brand span { color: #52d49f; }
    .hero-title-row {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 32px;
      margin-top: 17px;
    }
    .hero-main { min-width: 0; }
    .eyebrow {
      color: #75caa7;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: .04em;
    }
    h1 {
      max-width: 1250px;
      margin: 3px 0 0;
      font-size: clamp(27px, 3vw, 43px);
      line-height: 1.15;
      letter-spacing: -.035em;
      overflow-wrap: anywhere;
    }
    .hero-summary {
      max-width: 1150px;
      margin: 9px 0 0;
      color: #c2d8ce;
      font-size: 13px;
    }
    .hero-total {
      flex: 0 0 auto;
      min-width: 200px;
      padding: 12px 15px;
      border: 1px solid rgba(134, 213, 179, .28);
      border-radius: 13px;
      background: rgba(9, 67, 46, .6);
      text-align: right;
    }
    .hero-total span { display: block; color: #a9c9bb; font-size: 11px; }
    .hero-total strong {
      display: block;
      margin-top: 2px;
      font: 700 23px ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    .breadcrumb {
      display: flex;
      flex-wrap: wrap;
      gap: 3px 0;
      margin: 14px 0 0;
      padding: 0;
      list-style: none;
      color: #a9c3b7;
      font-size: 11px;
    }
    .breadcrumb li { overflow-wrap: anywhere; }
    .breadcrumb li:not(:last-child)::after {
      content: "›";
      padding: 0 7px;
      color: #5c8d78;
    }
    .hero-status {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 7px 18px;
      margin-top: 15px;
      color: #bad2c7;
      font-size: 11px;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 5px 10px;
      border: 1px solid rgba(98, 194, 153, .28);
      border-radius: 999px;
      background: rgba(16, 83, 59, .48);
    }
    .status-dot { width: 7px; height: 7px; border-radius: 50%; background: #61d5a2; }
    .toolbar-wrap {
      position: relative;
      z-index: 20;
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }
    .toolbar {
      display: flex;
      max-width: 1740px;
      margin: 0 auto;
      padding: 12px 24px;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }
    .search-shell { position: relative; flex: 1 1 620px; }
    .search-input {
      width: 100%;
      min-height: 44px;
      padding: 9px 14px 9px 40px;
      border: 1px solid var(--line-strong);
      border-radius: 10px;
      color: var(--ink);
      background: var(--surface-soft);
    }
    .search-icon {
      position: absolute;
      top: 12px;
      left: 14px;
      color: var(--muted);
      pointer-events: none;
    }
    .search-results {
      position: absolute;
      z-index: 30;
      top: calc(100% + 6px);
      left: 0;
      right: 0;
      overflow: hidden;
      max-height: 410px;
      border: 1px solid var(--line-strong);
      border-radius: 11px;
      background: var(--surface);
      box-shadow: var(--shadow);
    }
    .search-results[hidden] { display: none; }
    .result-button {
      display: grid;
      width: 100%;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 5px 18px;
      padding: 10px 13px;
      border: 0;
      border-bottom: 1px solid var(--line);
      color: var(--ink);
      background: transparent;
      text-align: left;
      cursor: pointer;
    }
    .result-button:last-child { border-bottom: 0; }
    .result-button:hover, .result-button[aria-selected="true"] { background: var(--brand-soft); }
    .result-title { font-weight: 700; overflow-wrap: anywhere; }
    .result-meta { color: var(--muted); font-size: 11px; }
    .result-amount { grid-row: 1 / span 2; grid-column: 2; align-self: center; font-weight: 700; }
    .toolbar-actions { display: flex; gap: 7px; flex: 0 0 auto; }
    .tool-button, .tool-link {
      display: inline-flex;
      min-height: 42px;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 8px 11px;
      border: 1px solid var(--line);
      border-radius: 9px;
      color: var(--ink);
      background: var(--surface-soft);
      text-decoration: none;
      cursor: pointer;
      white-space: nowrap;
    }
    .tool-button:hover, .tool-link:hover { border-color: var(--brand); background: var(--brand-soft); }
    main { max-width: 1740px; margin: 0 auto; padding: 18px 24px 52px; }
    .section-heading {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 18px;
      margin-bottom: 10px;
    }
    h2 { margin: 0; font-size: 19px; letter-spacing: -.02em; }
    .section-kicker { margin-top: 3px; color: var(--muted); font-size: 12px; }
    .map-counts { color: var(--muted); font-size: 11px; text-align: right; }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 7px 15px;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 11px;
    }
    .legend-item { display: inline-flex; align-items: center; gap: 6px; }
    .legend-line { width: 31px; height: 0; border-top: 2px solid var(--edge-flow); }
    .legend-line.classification { border-color: var(--edge-class); }
    .legend-line.crosswalk { border-color: var(--edge-cross); border-top-style: dashed; }
    .legend-line.candidate { border-color: var(--edge-candidate); border-top-style: dashed; }
    .legend-chip {
      display: inline-block;
      width: 14px;
      height: 14px;
      border-radius: 4px;
      border: 1px solid var(--brand);
      background: var(--brand-soft);
    }
    .map-scroll {
      overflow-x: auto;
      border: 1px solid var(--line-strong);
      border-radius: 12px;
      background: var(--surface-soft);
      box-shadow: var(--shadow);
    }
    .budget-board { position: relative; min-width: 1320px; background: var(--surface); }
    .lane-header {
      position: relative;
      z-index: 3;
      display: grid;
      grid-template-columns: 108px repeat(5, minmax(0, 1fr));
      border-bottom: 1px solid var(--line-strong);
      background: var(--surface);
    }
    .lane-corner, .lane-title { min-height: 68px; padding: 12px; border-left: 1px solid var(--line); }
    .lane-corner { border-left: 0; color: var(--muted); font-size: 11px; }
    .lane-corner b { display: block; color: var(--ink); font-size: 12px; }
    .lane-title { border-top: 5px solid var(--line-strong); }
    .lane-title:nth-child(2) { border-top-color: var(--brand); }
    .lane-title:nth-child(3) { border-top-color: var(--blue); }
    .lane-title:nth-child(4) { border-top-color: var(--amber); }
    .lane-title:nth-child(5) { border-top-color: var(--brown); }
    .lane-title:nth-child(6) { border-top-color: var(--violet); }
    .lane-title strong { display: block; font-size: 13px; }
    .lane-title span { display: block; margin-top: 3px; color: var(--muted); font-size: 10px; }
    .stages { position: relative; z-index: 2; }
    .stage-row {
      display: grid;
      min-height: 180px;
      grid-template-columns: 108px repeat(5, minmax(0, 1fr));
      border-bottom: 1px solid var(--line);
    }
    .stage-row:nth-child(even) { background: color-mix(in srgb, var(--surface-soft) 74%, transparent); }
    .stage-row:last-child { border-bottom: 0; }
    .gate {
      padding: 16px 12px;
      border-right: 1px solid var(--line);
      background: var(--surface-strong);
    }
    .gate-code { display: block; color: var(--brand); font: 700 11px ui-monospace, SFMono-Regular, Menlo, monospace; }
    .gate-name { display: block; margin-top: 4px; font-size: 13px; font-weight: 800; }
    .gate-note { display: block; margin-top: 5px; color: var(--muted); font-size: 10px; }
    .lane-cell {
      position: relative;
      display: flex;
      min-width: 0;
      flex-direction: column;
      gap: 10px;
      padding: 16px 14px;
      border-right: 1px solid var(--line);
    }
    .lane-cell:last-child { border-right: 0; }
    .money-card {
      position: relative;
      z-index: 4;
      display: block;
      width: 100%;
      min-height: 88px;
      padding: 9px 10px 10px 13px;
      border: 1px solid var(--line-strong);
      border-left: 4px solid var(--line-strong);
      border-radius: 9px;
      color: var(--ink);
      background: var(--surface);
      box-shadow: 0 3px 9px rgba(30, 54, 43, .08);
      text-align: left;
      cursor: pointer;
    }
    .money-card:hover { border-color: var(--brand); }
    .money-card[aria-pressed="true"] { outline: 3px solid color-mix(in srgb, var(--brand) 38%, transparent); outline-offset: 2px; }
    .money-card.type-source { border-left-color: var(--brand); background: var(--brand-soft); }
    .money-card.type-core { border-color: var(--brand-strong); border-left-color: var(--brand-strong); color: var(--header-ink); background: var(--brand-strong); }
    .money-card.type-core .node-kicker, .money-card.type-core .node-meta { color: #c2ddd1; }
    .money-card.type-item { border-left-color: var(--blue); }
    .money-card.type-channel { border-left-color: var(--brown); background: var(--brown-soft); }
    .money-card.type-destination { border-left-color: var(--violet); background: var(--violet-soft); }
    .money-card.type-candidate { border-left-color: var(--blue); border-style: dashed; background: var(--blue-soft); }
    .money-card.type-beneficiary { border-left-color: var(--violet); background: var(--violet-soft); }
    .money-card.type-reconcile { border-left-color: var(--brand); background: var(--brand-soft); }
    .money-card.type-unknown { border-left-color: var(--amber); background: var(--amber-soft); }
    .node-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .node-kicker { color: var(--muted); font: 700 9px ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: .02em; }
    .node-badge {
      flex: 0 0 auto;
      padding: 2px 6px;
      border-radius: 999px;
      color: var(--muted);
      background: var(--surface-strong);
      font-size: 9px;
      font-weight: 700;
    }
    .node-title { display: block; margin-top: 5px; font-size: 12px; font-weight: 800; line-height: 1.35; overflow-wrap: anywhere; }
    .node-meta { display: block; margin-top: 4px; color: var(--muted); font-size: 10px; line-height: 1.42; overflow-wrap: anywhere; }
    .node-amount { display: block; margin-top: 7px; font: 700 12px ui-monospace, SFMono-Regular, Menlo, monospace; text-align: right; }
    .mini-bar { display: flex; overflow: hidden; height: 4px; margin-top: 8px; border-radius: 4px; background: var(--surface-strong); }
    .mini-segment { min-width: 2px; background: var(--blue); }
    .mini-segment:nth-child(2) { background: var(--brand); }
    .mini-segment:nth-child(3) { background: var(--amber); }
    .mini-segment:nth-child(4) { background: var(--violet); }
    .mini-segment.fund-national { background: var(--blue); }
    .mini-segment.fund-sido { background: var(--brand); }
    .mini-segment.fund-sigungu { background: var(--amber); }
    .mini-segment.fund-other { background: var(--violet); }
    .edge-layer { position: absolute; z-index: 3; inset: 0; width: 100%; height: 100%; pointer-events: none; overflow: visible; }
    .edge { fill: none; stroke-width: 1.8; opacity: .82; transition: opacity .15s ease, stroke-width .15s ease; }
    .edge-flow { stroke: var(--edge-flow); marker-end: url(#arrow-flow); }
    .edge-classification { stroke: var(--edge-class); marker-end: url(#arrow-class); }
    .edge-crosswalk { stroke: var(--edge-cross); stroke-dasharray: 6 5; marker-end: url(#arrow-cross); }
    .edge-candidate { stroke: var(--edge-candidate); stroke-dasharray: 5 5; marker-end: url(#arrow-candidate); }
    .edge-context { stroke: var(--edge-context); stroke-dasharray: 2 5; marker-end: url(#arrow-context); }
    .edge.is-dim { opacity: .08; }
    .edge.is-active { opacity: 1; stroke-width: 3.1; }
    .selected-detail {
      min-height: 42px;
      margin-top: 10px;
      padding: 10px 13px;
      border-left: 4px solid var(--brand);
      color: var(--muted);
      background: var(--surface-strong);
      font-size: 12px;
    }
    .selected-detail strong { color: var(--ink); }
    .analysis-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(320px, .7fr);
      gap: 14px;
      margin-top: 18px;
    }
    .analysis-panel {
      min-width: 0;
      padding: 15px;
      border: 1px solid var(--line);
      border-radius: 11px;
      background: var(--surface);
    }
    .analysis-panel h2 { font-size: 16px; }
    .analysis-sub { margin: 3px 0 12px; color: var(--muted); font-size: 11px; }
    .reconcile-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .reconcile-row { padding: 9px 10px; background: var(--surface-soft); border-left: 3px solid var(--line-strong); }
    .reconcile-row.ok { border-left-color: var(--brand); }
    .reconcile-row span { display: block; color: var(--muted); font-size: 10px; }
    .reconcile-row strong { display: block; margin-top: 2px; font-size: 13px; }
    .insight-list { margin: 13px 0 0; padding-left: 19px; font-size: 12px; }
    .insight-list li + li { margin-top: 7px; }
    .source-list { display: grid; gap: 8px; }
    .source-row { padding: 9px 10px; border-left: 3px solid var(--violet); background: var(--surface-soft); font-size: 11px; }
    .source-row strong { display: block; font-size: 12px; }
    .source-row span { display: block; margin-top: 2px; color: var(--muted); overflow-wrap: anywhere; }
    .warning-list { margin: 12px 0 0; padding: 10px 12px 10px 30px; color: var(--danger); background: var(--danger-soft); font-size: 11px; }
    .table-wrap { overflow-x: auto; margin-top: 18px; }
    table { width: 100%; border-collapse: collapse; font-size: 11px; }
    caption { margin-bottom: 7px; color: var(--muted); text-align: left; }
    th, td { padding: 8px 7px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-weight: 700; }
    td.amount { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 700; text-align: right; white-space: nowrap; }
    .candidate-note { margin-top: 10px; color: var(--muted); font-size: 10px; }
    .local-overview {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 7px;
      margin-top: 13px;
    }
    .local-stat { padding: 8px 9px; border-left: 3px solid var(--blue); background: var(--blue-soft); }
    .local-stat span { display: block; color: var(--muted); font-size: 10px; }
    .local-stat strong { display: block; margin-top: 2px; font-size: 12px; }
    .funding-cell { min-width: 165px; }
    .funding-track { display: flex; overflow: hidden; height: 7px; margin-bottom: 4px; border-radius: 5px; background: var(--surface-strong); }
    .funding-track span { min-width: 1px; }
    .funding-national { background: var(--blue); }
    .funding-sido { background: var(--brand); }
    .funding-sigungu { background: var(--amber); }
    .funding-other { background: var(--violet); }
    .funding-text { color: var(--muted); font-size: 10px; white-space: nowrap; }
    .match-text { color: var(--muted); font-size: 10px; }
    footer { max-width: 1740px; margin: 0 auto; padding: 0 24px 28px; color: var(--muted); font-size: 10px; }
    .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
    @media (prefers-reduced-motion: reduce) {
      html { scroll-behavior: auto; }
      .edge { transition: none; }
    }
    @media (max-width: 1100px) {
      .hero-title-row { align-items: start; flex-direction: column; }
      .hero-total { width: 100%; text-align: left; }
      .toolbar { align-items: stretch; flex-direction: column; }
      .search-shell { flex: 0 0 auto; width: 100%; }
      .toolbar-actions { display: grid; grid-template-columns: repeat(3, 1fr); }
      .analysis-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 640px) {
      .hero-inner, .toolbar, main { padding-left: 14px; padding-right: 14px; }
      .hero-top { align-items: start; flex-direction: column; gap: 3px; }
      h1 { font-size: 28px; }
      .toolbar-actions { grid-template-columns: 1fr; }
      .section-heading { align-items: start; flex-direction: column; }
      .map-counts { text-align: left; }
      .map-scroll { overflow: visible; border: 0; box-shadow: none; background: transparent; }
      .budget-board { min-width: 0; background: transparent; }
      .lane-header, .edge-layer { display: none; }
      .stage-row {
        display: block;
        min-height: 0;
        margin-bottom: 11px;
        border: 1px solid var(--line);
        border-radius: 10px;
        background: var(--surface);
      }
      .gate { border-right: 0; border-bottom: 1px solid var(--line); }
      .lane-cell { padding: 10px; border-right: 0; border-bottom: 1px solid var(--line); }
      .lane-cell:empty { display: none; }
      .lane-cell:not(:empty)::before {
        content: attr(data-lane-label);
        color: var(--muted);
        font-size: 10px;
        font-weight: 700;
      }
      .reconcile-list { grid-template-columns: 1fr; }
      .local-overview { grid-template-columns: 1fr; }
    }
    @media print {
      @page { size: A3 landscape; margin: 8mm; }
      :root { color-scheme: light; --page: #fff; --surface: #fff; --surface-soft: #f7f7f3; --surface-strong: #e9eee9; --ink: #111; --muted: #444; --line: #aaa; --line-strong: #777; }
      body { background: #fff; }
      .skip-link, .toolbar-wrap, .selected-detail, footer { display: none !important; }
      .hero { background: #08271b !important; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
      main { max-width: none; padding: 12px 0; }
      .map-scroll { overflow: visible; box-shadow: none; }
      .budget-board { min-width: 1200px; }
      .money-card, .analysis-panel, .stage-row { break-inside: avoid; }
      .analysis-grid { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#budget-map">예산체계도로 건너뛰기</a>
  <header class="hero">
    <div class="hero-inner">
      <div class="hero-top">
        <div class="brand">대한민국 예산 <span>100</span> · 돈의 구조도</div>
        <div>기준: __YEAR__ 본예산 국회확정 · 열린재정 Add2</div>
      </div>
      <div class="hero-title-row">
        <div class="hero-main">
          <div class="eyebrow" id="business-code">예산체계도 · 세부사업</div>
          <h1 id="business-title">세부사업 불러오는 중</h1>
          <p class="hero-summary" id="business-summary"></p>
        </div>
        <div class="hero-total">
          <span>국회확정액</span>
          <strong id="business-total">-</strong>
        </div>
      </div>
      <ol class="breadcrumb" id="breadcrumb" aria-label="예산 계층"></ol>
      <div class="hero-status" id="hero-status"></div>
    </div>
  </header>

  <div class="toolbar-wrap">
    <div class="toolbar">
      <div class="search-shell">
        <span class="search-icon" aria-hidden="true">⌕</span>
        <label class="sr-only" for="business-search">세부사업 검색</label>
        <input class="search-input" id="business-search" type="search" autocomplete="off"
          placeholder="1,401개 사업에서 사업명·부처·회계·프로그램 검색"
          aria-controls="search-results" aria-expanded="false" />
        <div class="search-results" id="search-results" role="listbox" hidden></div>
      </div>
      <div class="toolbar-actions">
        <button class="tool-button" id="print-button" type="button">현재 체계도 인쇄</button>
        <a class="tool-link" href="detail_business_structure.html">전체 예산 계층</a>
        <a class="tool-link" href="detailed_business_workflows.html">업무 절차 · 보조</a>
      </div>
    </div>
  </div>

  <main id="budget-map">
    <section aria-labelledby="map-heading">
      <div class="section-heading">
        <div>
          <h2 id="map-heading">확정재원이 갈라지고 닿는 구조</h2>
          <div class="section-kicker">중앙 확정재원 → 내역사업 → 목·세목·집행채널 → 지방 편성·재원구성 → 지출·수혜·검증</div>
        </div>
        <div class="map-counts" id="map-counts"></div>
      </div>
      <div class="legend" aria-label="체계도 범례">
        <span class="legend-item"><i class="legend-chip" aria-hidden="true"></i>확정·문서 근거 노드</span>
        <span class="legend-item"><i class="legend-line" aria-hidden="true"></i>금액 포함·배분</span>
        <span class="legend-item"><i class="legend-line classification" aria-hidden="true"></i>세목→채널 분류</span>
        <span class="legend-item"><i class="legend-line crosswalk" aria-hidden="true"></i>PDF↔API 직접 대사</span>
        <span class="legend-item"><i class="legend-line candidate" aria-hidden="true"></i>LOFIN 후보·비가산</span>
      </div>
      <div class="map-scroll" tabindex="0" role="region" aria-label="예산체계도, 작은 화면에서는 좌우로 스크롤 가능">
        <div class="budget-board" id="board">
          <div class="lane-header" aria-hidden="true">
            <div class="lane-corner"><b>계층 ↓</b>돈의 위치 →</div>
            <div class="lane-title"><strong>재원·회계</strong><span>국회확정 · 회계·분야</span></div>
            <div class="lane-title"><strong>세부사업·내역</strong><span>사업 총액 · PDF 산출근거</span></div>
            <div class="lane-title"><strong>목·세목</strong><span>Add2 국회확정액 정본</span></div>
            <div class="lane-title"><strong>집행채널</strong><span>보조·위탁·출연·계약·직접</span></div>
            <div class="lane-title"><strong>기관·지역·수혜</strong><span>지방 편성·지출과 수혜 근거</span></div>
          </div>
          <svg class="edge-layer" id="edge-layer" aria-hidden="true"></svg>
          <div class="stages" id="stages"></div>
        </div>
      </div>
      <div class="selected-detail" id="selected-detail" aria-live="polite">
        카드 하나를 선택하면 금액·근거·연결 상태를 여기에 표시합니다.
      </div>
    </section>

    <div class="analysis-grid">
      <section class="analysis-panel" aria-labelledby="reconcile-heading">
        <h2 id="reconcile-heading">금액 대사와 해석</h2>
        <p class="analysis-sub">같은 총액을 내역사업과 회계 세목 두 방향에서 확인합니다.</p>
        <div class="reconcile-list" id="reconcile-list"></div>
        <ul class="insight-list" id="insight-list"></ul>
        <div class="table-wrap" id="item-table-wrap"></div>
      </section>
      <aside class="analysis-panel" aria-labelledby="source-heading">
        <h2 id="source-heading">지방재정·근거</h2>
        <p class="analysis-sub">지역 편성·재원구성·지출 스냅샷과 연결 근거를 함께 읽습니다.</p>
        <div class="source-list" id="source-list"></div>
        <ul class="warning-list" id="warning-list" hidden></ul>
        <div id="candidate-table-wrap"></div>
      </aside>
    </div>
  </main>

  <footer>
    Koreabudget100 · 금액 정본: Open Fiscal ExpenditureBudgetAdd2 / Y_YY_DFN_KCUR_AMT ·
    PDF: 확정 매칭 설명자료 · LOFIN QWGJK: 지역 예산현액·재원구성·지출 스냅샷 · keyword_candidate, 비가산 · 중앙 교부처 확정표가 아닙니다.
  </footer>

  <script id="budget-data" type="application/json">__PAYLOAD__</script>
  <script>
    'use strict';
    const DATA = JSON.parse(document.getElementById('budget-data').textContent);
    const MAPS = Array.isArray(DATA.maps) ? DATA.maps : [];
    const META = DATA.meta || {};
    const BY_ID = new Map(MAPS.map(row => [String(row.id), row]));
    const LANES = ['재원·회계', '세부사업·내역', '목·세목', '집행채널', '기관·지역·수혜'];
    const SVG_NS = 'http://www.w3.org/2000/svg';
    const state = { current: null, nodes: new Map(), edges: [], selectedNode: '', searchRows: [], searchIndex: -1 };

    const byId = id => document.getElementById(id);
    const array = value => Array.isArray(value) ? value : [];
    const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
    const text = value => value == null ? '' : String(value);
    const object = value => value && typeof value === 'object' ? value : {};
    const normalize = value => text(value).normalize('NFKC').toLowerCase().replace(/[^0-9a-z가-힣]+/g, '');
    const el = (tag, className, value) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (value != null) node.textContent = text(value);
      return node;
    };
    const svgEl = tag => document.createElementNS(SVG_NS, tag);

    function won(value, exact = false) {
      const amount = number(value);
      const abs = Math.abs(amount);
      if (!amount) return exact ? '0원' : '0원';
      if (abs >= 1e12) {
        const trillion = amount / 1e12;
        return `${trillion.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}조원`;
      }
      if (abs >= 1e8) {
        const digits = exact && abs < 1e11 ? 2 : 1;
        return `${(amount / 1e8).toLocaleString('ko-KR', { maximumFractionDigits: digits })}억원`;
      }
      if (abs >= 1e6) return `${(amount / 1e6).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}백만원`;
      return `${amount.toLocaleString('ko-KR')}원`;
    }

    function percent(part, total) {
      return total ? `${(number(part) * 100 / number(total)).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%` : '0%';
    }

    function dateLabel(value) {
      const raw = text(value).replace(/\D/g, '');
      return raw.length === 8 ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}` : text(value || '기준일 미상');
    }

    function rateLabel(value) {
      return value == null ? '산정 불가' : `${(number(value) * 100).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%`;
    }

    function fundingComponents(row) {
      return [
        { kind: 'national', label: '국비', amount_won: number(row.national_amt) },
        { kind: 'sido', label: '시도비', amount_won: number(row.sido_amt) },
        { kind: 'sigungu', label: '시군구비', amount_won: number(row.sigungu_amt) },
        { kind: 'other', label: '기타', amount_won: number(row.other_amt) },
      ].filter(component => component.amount_won > 0);
    }

    function makeNode(spec) {
      const node = {
        id: text(spec.id),
        type: text(spec.type || 'item'),
        kicker: text(spec.kicker),
        badge: text(spec.badge),
        title: text(spec.title),
        meta: text(spec.meta),
        amount: number(spec.amount),
        amountText: spec.amountText == null ? '' : text(spec.amountText),
        detail: text(spec.detail || spec.meta),
        components: array(spec.components),
        source: text(spec.source),
      };
      state.nodes.set(node.id, node);
      return node;
    }

    function card(node) {
      const button = el('button', `money-card type-${node.type}`);
      button.type = 'button';
      button.dataset.nodeId = node.id;
      button.setAttribute('aria-pressed', 'false');
      const top = el('span', 'node-top');
      top.append(el('span', 'node-kicker', node.kicker), el('span', 'node-badge', node.badge));
      button.append(top, el('span', 'node-title', node.title));
      if (node.meta) button.append(el('span', 'node-meta', node.meta));
      if (node.amount || node.amountText) {
        button.append(el('span', 'node-amount', node.amountText || won(node.amount, true)));
      }
      if (node.components.length && node.amount) {
        const bar = el('span', 'mini-bar');
        node.components.forEach(component => {
          const segment = el('span', 'mini-segment');
          if (component.kind) segment.classList.add(`fund-${component.kind}`);
          segment.style.width = `${Math.max(1, number(component.amount_won) * 100 / node.amount)}%`;
          bar.append(segment);
        });
        button.append(bar);
      }
      return button;
    }

    function addEdge(from, to, type, amount, label) {
      if (!state.nodes.has(from) || !state.nodes.has(to)) return;
      state.edges.push({ from, to, type, amount: number(amount), label: text(label) });
    }

    function stage(code, name, note, laneNodes) {
      const section = el('section', 'stage-row');
      section.dataset.stage = code;
      const gate = el('div', 'gate');
      gate.append(
        el('span', 'gate-code', code),
        el('span', 'gate-name', name),
        el('span', 'gate-note', note),
      );
      section.append(gate);
      for (let lane = 0; lane < 5; lane += 1) {
        const cell = el('div', 'lane-cell');
        cell.dataset.lane = String(lane);
        cell.dataset.laneLabel = LANES[lane];
        array(laneNodes[lane]).forEach(node => cell.append(card(node)));
        section.append(cell);
      }
      return section;
    }

    function renderMap(map) {
      state.current = map;
      state.nodes = new Map();
      state.edges = [];
      state.selectedNode = '';
      const core = object(map.core);
      const total = number(core.congress_amt);
      document.title = `${map.title} · 예산체계도`;
      byId('business-code').textContent = `${core.year || META.year} 예산체계도 · ${core.office_name || '소관 미상'}`;
      byId('business-title').textContent = `${map.title} — ${won(total, true)}의 물길`;
      const subCount = array(map.subprojects).length;
      const channelCount = array(map.channels).length;
      const basisSummary = object(map.budget_basis_summary);
      const localSummary = object(map.local_summary);
      const localCount = number(localSummary.candidate_count);
      const snapshotDate = array(localSummary.snapshot_dates)[0];
      const centralSummary = subCount
        ? `사업설명자료 내역 ${subCount}개와 열린재정 목·세목 ${array(map.budget_items).length}개를 따로 대사해 ${channelCount}개 집행채널로 연결합니다.`
        : basisSummary.text
          ? `사업설명자료 산출근거 문맥과 열린재정 목·세목 ${array(map.budget_items).length}개를 함께 읽고 ${channelCount}개 집행채널로 분류했습니다. 내역사업 금액은 임의로 쪼개지 않았습니다.`
          : `열린재정 목·세목 ${array(map.budget_items).length}개를 ${channelCount}개 집행채널로 분류했습니다. PDF 내역사업 자료가 없는 부분은 만들지 않았습니다.`;
      byId('business-summary').textContent = localCount
        ? `${centralSummary} LOFIN에서 ${dateLabel(snapshotDate)} 기준 지역 예산 편성·지출 후보 ${localCount}건을 확인했습니다.`
        : `${centralSummary} LOFIN 키워드 후보가 없는 지역은 추정하지 않았습니다.`;
      byId('business-total').textContent = won(total, true);
      renderBreadcrumb(core);
      renderHeroStatus(map);

      const source = makeNode({
        id: 'source-account', type: 'source', kicker: 'F0 · OF 정본', badge: '재원',
        title: core.account_name || '회계명 미상',
        meta: `${core.field_name || '분야 미상'} · ${core.section_name || '부문 미상'}`,
        amount: total, amountText: won(total, true), detail: `국회확정액의 회계·분야·부문 출처`, source: 'Open Fiscal Add2',
      });
      const business = makeNode({
        id: 'business-core', type: 'core', kicker: 'B0 · OF 정본', badge: '세부사업',
        title: map.title, meta: `${core.program_name || '프로그램 미상'} · ${core.unit_business_name || '단위사업 미상'}`,
        amount: total, amountText: won(total, true), detail: `${core.office_name || '소관 미상'} 세부사업 국회확정액`, source: 'Open Fiscal Add2',
      });
      addEdge(source.id, business.id, 'flow', total, '확정재원');

      const subNodes = [];
      if (subCount) {
        array(map.subprojects).forEach((row, index) => {
          const node = makeNode({
            id: `sub-${row.id}`, type: 'item', kicker: `${row.marker || index + 1} · PDF`, badge: '내역사업',
            title: row.label, meta: row.summary || text(row.detail).slice(0, 105), amount: row.amount_won,
            detail: row.detail, components: row.components, source: array(row.source_refs).join(', '),
          });
          subNodes.push(node);
          addEdge(business.id, node.id, 'flow', row.amount_won, '내역 배분');
        });
      } else {
        subNodes.push(basisSummary.text ? makeNode({
          id: 'basis-summary', type: 'item', kicker: 'PDF · 산출근거', badge: '문맥 확인',
          title: basisSummary.label || 'PDF 예산 산출근거', meta: basisSummary.text.slice(0, 180),
          amountText: `세부사업 총액 ${won(total, true)}`,
          detail: basisSummary.text, source: basisSummary.source_ref,
        }) : makeNode({
          id: 'sub-unknown', type: 'unknown', kicker: 'PDF 미확보', badge: '자료없음',
          title: '내역사업 배분 근거 없음', meta: '사업 총액을 임의로 쪼개지 않았습니다.',
          detail: 'PDF 산출근거가 확정 매칭되지 않아 내역사업 노드를 생성하지 않음',
        }));
      }

      const itemNodes = array(map.budget_items).map((row, index) => {
        const node = makeNode({
          id: `api-${row.id}`, type: 'item', kicker: `A${String(index + 1).padStart(2, '0')} · OF`, badge: '국회확정',
          title: row.semok_name, meta: `${row.mok_name} · ${percent(row.amount_won, total)}`,
          amount: row.amount_won,
          detail: `${row.mok_name} > ${row.semok_name} · ${row.amount_field} · 원자료 ${row.line_count}행`,
          source: row.source,
        });
        addEdge(business.id, node.id, 'flow', row.amount_won, '세목 배분');
        return node;
      });
      if (!itemNodes.length) itemNodes.push(makeNode({
        id: 'api-no-items', type: 'unknown', kicker: 'OF · 국회확정', badge: '0원',
        title: '확정 목·세목 없음', meta: '국회확정액이 0원인 세부사업입니다.',
        amountText: '0원', detail: 'Add2 국회확정 목·세목 금액 없음', source: 'Open Fiscal Add2',
      }));

      const channelNodes = array(map.channels).map((row, index) => {
        const note = [row.description, row.support_rate ? `지원율 ${row.support_rate}` : ''].filter(Boolean).join(' · ');
        const node = makeNode({
          id: row.id, type: 'channel', kicker: `C${String(index + 1).padStart(2, '0')} · 세목분류`, badge: '집행채널',
          title: row.label, meta: note, amount: row.amount_won,
          detail: `${row.description}${row.destination_note ? ` · ${row.destination_note}` : ''}`,
          source: 'Add2 세목 규칙',
        });
        array(row.item_ids).forEach(itemId => addEdge(`api-${itemId}`, node.id, 'classification', 0, '세목→채널'));
        return node;
      });
      if (!channelNodes.length) channelNodes.push(makeNode({
        id: 'channel-none', type: 'unknown', kicker: 'C00 · 미생성', badge: '0원',
        title: '집행채널 없음', meta: '확정 목·세목이 없어 채널을 만들지 않았습니다.',
        amountText: '0원', detail: '금액 없는 사업에 집행채널을 추정하지 않음',
      }));
      array(map.crosswalks).forEach(row => {
        addEdge(`sub-${row.subproject_id}`, row.channel_id, 'crosswalk', row.amount_won, row.note);
      });

      const destinationNodes = array(map.channels).map((row, index) => {
        const genericUnknown = !row.destination_note && !row.support_rate;
        const node = makeNode({
          id: `dest-${row.code}`, type: genericUnknown ? 'unknown' : 'destination',
          kicker: `D${String(index + 1).padStart(2, '0')} · ${genericUnknown ? '수급자 미상' : '문서 보강'}`,
          badge: genericUnknown ? '기관 미상' : '집행대상', title: row.destination,
          meta: row.destination_note || '세목 유형은 확인되나 실제 수급 기관·지역은 자료에서 특정되지 않음',
          amount: row.amount_won, detail: row.destination_note || row.description,
          source: genericUnknown ? '세목 유형만 확인' : object(map.implementation).source_ref,
        });
        addEdge(row.id, node.id, 'flow', row.amount_won, '집행대상');
        return node;
      });

      const localSummaryNode = makeNode(localCount ? {
        id: 'lofin-summary', type: 'candidate', kicker: 'LF · QWGJK', badge: '편성·지출 후보',
        title: `지역 세부사업 ${localCount}건`,
        meta: `광역 ${number(localSummary.wide_area_row_count)} · 기초 ${number(localSummary.basic_row_count)} · ${number(localSummary.unique_local_gov_count)}개 지자체`,
        amountText: `${dateLabel(snapshotDate)} 관측 · 비가산`,
        detail: `PDF 내역 또는 중앙 세부사업명 키워드로 찾은 지방 예산현액·재원구성·지출액 스냅샷. 중앙 교부처 확정 관계가 아니며 관측합은 중복될 수 있음`,
        source: 'LOFIN QWGJK',
      } : {
        id: 'lofin-summary', type: 'unknown', kicker: 'LF · QWGJK', badge: '후보 없음',
        title: '지역 편성 후보 미확인',
        meta: '중앙사업·PDF 내역 키워드에서 양수 국비 지역 행을 찾지 못함',
        amountText: '지역명 추정 안 함',
        detail: 'LOFIN 조회 결과가 없다는 뜻이며 지방 집행이 없다고 단정하지 않음',
        source: 'LOFIN QWGJK',
      });
      const localChannel = array(map.channels).find(row => row.code === 'local_subsidy');
      if (localCount && localChannel) addEdge(localChannel.id, localSummaryNode.id, 'candidate', 0, '지자체이전 세목→지역 관측');
      if (localCount) {
        array(localSummary.matched_subproject_ids).forEach(subprojectId => {
          addEdge(`sub-${subprojectId}`, localSummaryNode.id, 'candidate', 0, 'PDF 내역명→LOFIN 검색');
        });
      }

      const localRegionNodes = array(map.local_groups).map((row, index) => {
        const execution = row.execution_rate == null ? '집행률 산정 불가' : `관측 집행률 ${rateLabel(row.execution_rate)}`;
        const node = makeNode({
          id: row.id || `local-region-${index + 1}`, type: 'candidate',
          kicker: `L${String(index + 1).padStart(2, '0')} · ${row.region_name || '권역 미상'}`, badge: '지역 관측',
          title: `${row.region_name || '권역 미상'} · ${number(row.row_count)}개 지방사업`,
          meta: `지자체 ${number(row.local_gov_count)} · 광역행 ${number(row.wide_area_row_count)} · 기초행 ${number(row.basic_row_count)}`,
          amount: row.budget_cash_amt,
          amountText: `예산현액 ${won(row.budget_cash_amt, true)} · 지출 ${won(row.spend_amt, true)}`,
          detail: `${execution} · 국비 ${won(row.national_amt, true)} · 시도비 ${won(row.sido_amt, true)} · 시군구비 ${won(row.sigungu_amt, true)} · 관측합 중복 가능`,
          components: fundingComponents(row), source: 'LOFIN QWGJK',
        });
        addEdge(localSummaryNode.id, node.id, 'candidate', 0, '권역별 관측');
        return node;
      });
      if (localCount && number(map.local_group_total_count) > localRegionNodes.length) {
        const omitted = number(map.local_group_total_count) - localRegionNodes.length;
        const more = makeNode({
          id: 'local-region-more', type: 'candidate', kicker: 'LF · 나머지', badge: '상세표 참조',
          title: `그 밖의 ${omitted}개 권역`, meta: '아래 지역재정 표에서 전체 관측행 확인',
          amountText: '관측합 비가산', detail: '보드에는 국비 관측액 상위 권역만 표시', source: 'LOFIN QWGJK',
        });
        addEdge(localSummaryNode.id, more.id, 'candidate', 0, '나머지 권역');
        localRegionNodes.push(more);
      }

      const implementation = object(map.implementation);
      const beneficiary = makeNode({
        id: 'beneficiary', type: implementation.beneficiary ? 'beneficiary' : 'unknown',
        kicker: 'R0 · PDF', badge: implementation.beneficiary ? '수혜자' : '자료없음',
        title: implementation.beneficiary || '수혜자 미확인',
        meta: implementation.implementer ? `시행주체: ${implementation.implementer}` : '사업설명자료의 수혜자 항목 미확인',
        detail: implementation.method ? `시행방법: ${implementation.method}` : '수혜·시행 구조 자료 없음',
        source: implementation.source_ref,
      });
      destinationNodes.filter(node => node.type !== 'candidate').forEach(node => addEdge(node.id, beneficiary.id, 'context', 0, '수혜 연결'));

      const reconciliation = object(map.reconciliation);
      const apiRecon = makeNode({
        id: 'reconcile-api', type: reconciliation.budget_items_reconciled ? 'reconcile' : 'unknown',
        kicker: 'V1 · API 대사', badge: reconciliation.budget_items_reconciled ? '차이 0원' : '불일치',
        title: '세부사업 총액 = 목·세목 합계',
        meta: `${won(reconciliation.business_total_won, true)} ↔ ${won(reconciliation.budget_item_total_won, true)}`,
        amountText: `차이 ${number(reconciliation.budget_item_difference_won).toLocaleString('ko-KR')}원`,
        detail: '국회확정액과 Add2 세목 합계를 원 단위로 대사', source: 'Open Fiscal Add2',
      });
      const pdfRecon = makeNode({
        id: 'reconcile-pdf', type: reconciliation.subprojects_reconciled ? 'reconcile' : 'unknown',
        kicker: 'V2 · PDF 대사', badge: reconciliation.subprojects_reconciled ? '차이 0원' : '미확보',
        title: reconciliation.subproject_total_won ? '세부사업 총액 = 내역사업 합계' : '내역사업 합계 자료 없음',
        meta: reconciliation.subproject_total_won ? `${won(reconciliation.business_total_won, true)} ↔ ${won(reconciliation.subproject_total_won, true)}` : 'PDF 산출근거 확정 매칭 없음',
        amountText: reconciliation.subproject_difference_won == null ? '' : `차이 ${number(reconciliation.subproject_difference_won).toLocaleString('ko-KR')}원`,
        detail: 'PDF 예산 산출근거의 내역사업 합계를 국회확정액과 대사', source: 'ministry PDF',
      });
      const localAudit = makeNode(localCount ? {
        id: 'reconcile-local', type: 'candidate', kicker: 'V3 · LOFIN 해석', badge: '비가산 검증',
        title: '지역 예산현액·지출 스냅샷',
        meta: `${dateLabel(snapshotDate)} · 예산현액 관측합 ${won(localSummary.observed_budget_cash_amt, true)} · 지출 ${won(localSummary.observed_spend_amt, true)}`,
        amountText: `관측 집행률 ${rateLabel(localSummary.observed_execution_rate)}`,
        detail: '관측행 내부의 예산현액 대비 지출 비율이며 광역·기초 중복 가능성 때문에 중앙 확정액과 비교하거나 대사하지 않음',
        source: 'LOFIN QWGJK',
      } : {
        id: 'reconcile-local', type: 'unknown', kicker: 'V3 · LOFIN 해석', badge: '자료 없음',
        title: '지역 스냅샷 미확인', meta: '조회 키워드에서 양수 국비 후보 행 없음',
        amountText: '중앙예산만 검증', detail: '지역명을 추정하거나 0원 집행으로 간주하지 않음', source: 'LOFIN QWGJK',
      });
      if (localCount) addEdge(localSummaryNode.id, localAudit.id, 'context', 0, '편성·지출 해석');

      const stages = byId('stages');
      stages.replaceChildren(
        stage('G0', '중앙 확정재원', '회계·분야와 세부사업 국회확정액', { 0: [source], 1: [business] }),
        stage('G1', '내역사업', 'PDF 산출근거의 사업별 배분', { 1: subNodes }),
        stage('G2', '목·세목·채널', '열린재정 회계 세목과 집행 유형', { 2: itemNodes, 3: channelNodes }),
        stage('G3', '중앙 집행대상', '세목·문서로 확인된 수급 유형과 미상 구분', { 4: destinationNodes }),
        stage('G4', '지방 편성 후보', 'LOFIN 예산현액과 국비·시도비·시군구비', { 3: [localSummaryNode], 4: localRegionNodes }),
        stage('G5', '지출·수혜·검증', '지역 지출 스냅샷, 수혜자 근거와 총액 대사', { 0: [localAudit], 1: [pdfRecon], 2: [apiRecon], 4: [beneficiary] }),
      );
      byId('map-counts').textContent = `내역 ${subCount || '자료없음'} · 세목 ${array(map.budget_items).length} · 채널 ${array(map.channels).length} · 지역관측 ${localCount || '없음'} · 직접 대사 ${array(map.crosswalks).length}`;
      renderAnalysis(map);
      requestAnimationFrame(() => {
        drawEdges();
        selectNode('business-core');
      });
    }

    function renderBreadcrumb(core) {
      const values = [core.year, core.office_name, core.account_name, core.field_name, core.section_name, core.program_name, core.unit_business_name, core.detail_business_name];
      const target = byId('breadcrumb');
      target.replaceChildren(...values.filter(Boolean).map(value => el('li', '', value)));
    }

    function renderHeroStatus(map) {
      const reconciliation = object(map.reconciliation);
      const target = byId('hero-status');
      target.replaceChildren();
      const pill = el('span', 'status-pill');
      pill.append(el('i', 'status-dot'), el('span', '', reconciliation.budget_items_reconciled ? 'API 세목 대사 완료 · 차이 0원' : 'API 세목 대사 확인 필요'));
      target.append(pill);
      target.append(el('span', '', `목·세목 ${array(map.budget_items).length}개`));
      target.append(el('span', '', `집행채널 ${array(map.channels).length}개`));
      target.append(el('span', '', `PDF 내역 ${array(map.subprojects).length || (object(map.budget_basis_summary).text ? '산출근거 문맥' : '자료없음')}`));
      const local = object(map.local_summary);
      const snapshot = array(local.snapshot_dates)[0];
      target.append(el('span', '', number(local.candidate_count)
        ? `LOFIN 지역 편성·지출 ${number(local.candidate_count)}건 · ${dateLabel(snapshot)}`
        : 'LOFIN 지역 후보 미확인'));
    }

    function marker(defs, id, color) {
      const node = svgEl('marker');
      node.setAttribute('id', id);
      node.setAttribute('viewBox', '0 0 10 10');
      node.setAttribute('refX', '8');
      node.setAttribute('refY', '5');
      node.setAttribute('markerWidth', '6');
      node.setAttribute('markerHeight', '6');
      node.setAttribute('orient', 'auto-start-reverse');
      const path = svgEl('path');
      path.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
      path.setAttribute('fill', color);
      node.append(path);
      defs.append(node);
    }

    function drawEdges() {
      const board = byId('board');
      const svg = byId('edge-layer');
      const boardRect = board.getBoundingClientRect();
      const width = board.scrollWidth;
      const height = board.scrollHeight;
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      svg.setAttribute('width', String(width));
      svg.setAttribute('height', String(height));
      svg.replaceChildren();
      const defs = svgEl('defs');
      marker(defs, 'arrow-flow', 'var(--edge-flow)');
      marker(defs, 'arrow-class', 'var(--edge-class)');
      marker(defs, 'arrow-cross', 'var(--edge-cross)');
      marker(defs, 'arrow-candidate', 'var(--edge-candidate)');
      marker(defs, 'arrow-context', 'var(--edge-context)');
      svg.append(defs);
      state.edges.forEach((edge, index) => {
        const from = board.querySelector(`[data-node-id="${CSS.escape(edge.from)}"]`);
        const to = board.querySelector(`[data-node-id="${CSS.escape(edge.to)}"]`);
        if (!from || !to) return;
        const a = from.getBoundingClientRect();
        const b = to.getBoundingClientRect();
        const ax = a.right - boardRect.left;
        const ay = a.top + a.height / 2 - boardRect.top;
        const bx = b.left - boardRect.left;
        const by = b.top + b.height / 2 - boardRect.top;
        const path = svgEl('path');
        const mid = ax <= bx ? ax + Math.max(20, (bx - ax) / 2) : Math.max(bx - 24, Math.min(ax + 24, width - 16));
        const d = ax <= bx
          ? `M ${ax} ${ay} L ${mid} ${ay} L ${mid} ${by} L ${bx} ${by}`
          : `M ${ax} ${ay} L ${mid} ${ay} L ${mid} ${by} L ${bx} ${by}`;
        path.setAttribute('d', d);
        path.setAttribute('class', `edge edge-${edge.type}`);
        path.dataset.edgeIndex = String(index);
        path.dataset.from = edge.from;
        path.dataset.to = edge.to;
        svg.append(path);
      });
      updateEdgeSelection();
    }

    function selectNode(nodeId) {
      if (!state.nodes.has(nodeId)) return;
      state.selectedNode = nodeId;
      document.querySelectorAll('.money-card').forEach(cardNode => {
        cardNode.setAttribute('aria-pressed', cardNode.dataset.nodeId === nodeId ? 'true' : 'false');
      });
      updateEdgeSelection();
      const node = state.nodes.get(nodeId);
      const relations = state.edges.filter(edge => edge.from === nodeId || edge.to === nodeId);
      const relationText = relations.length
        ? relations.map(edge => `${edge.from === nodeId ? '→' : '←'} ${edge.label}${edge.amount ? ` ${won(edge.amount, true)}` : ''}`).join(' · ')
        : '직접 연결선 없음';
      byId('selected-detail').replaceChildren(
        el('strong', '', `${node.title}${node.amount ? ` · ${won(node.amount, true)}` : ''}`),
        document.createTextNode(` — ${node.detail || '상세 근거 없음'} · ${relationText}`),
      );
    }

    function updateEdgeSelection() {
      document.querySelectorAll('.edge').forEach(path => {
        const active = !state.selectedNode || path.dataset.from === state.selectedNode || path.dataset.to === state.selectedNode;
        path.classList.toggle('is-active', active && Boolean(state.selectedNode));
        path.classList.toggle('is-dim', !active);
      });
    }

    function reconcileRow(label, value, note, ok) {
      const row = el('div', `reconcile-row${ok ? ' ok' : ''}`);
      row.append(el('span', '', label), el('strong', '', value), el('span', '', note));
      return row;
    }

    function renderAnalysis(map) {
      const rec = object(map.reconciliation);
      const reconcile = byId('reconcile-list');
      reconcile.replaceChildren(
        reconcileRow('세부사업 국회확정액', won(rec.business_total_won, true), '열린재정 정본', true),
        reconcileRow('목·세목 합계', won(rec.budget_item_total_won, true), `차이 ${number(rec.budget_item_difference_won).toLocaleString('ko-KR')}원`, rec.budget_items_reconciled),
        reconcileRow('PDF 내역사업 합계', rec.subproject_total_won ? won(rec.subproject_total_won, true) : '자료 없음', rec.subproject_total_won ? `차이 ${number(rec.subproject_difference_won).toLocaleString('ko-KR')}원` : '임의 배분 안 함', rec.subprojects_reconciled),
        reconcileRow('내역↔세목 직접 대사', won(rec.documented_crosswalk_won, true), `${percent(rec.documented_crosswalk_won, rec.business_total_won)}만 연결 · 나머지 추정 안 함`, true),
      );
      const insightList = byId('insight-list');
      const insights = array(map.insights);
      const defaults = [
        '목·세목 합계는 국회확정액과 원 단위로 검증합니다.',
        '집행채널은 세목 명칭에 따른 분류이며 실제 수급 기관은 문서가 있을 때만 표시합니다.',
        'PDF 내역사업이 없으면 총액을 임의 배분하지 않습니다.',
      ];
      if (number(object(map.local_summary).candidate_count)) {
        defaults.push('LOFIN 행은 지방 예산현액의 재원구성과 조회일 지출액을 보여 주되 중앙 확정액과는 대사하지 않습니다.');
      }
      insightList.replaceChildren(...(insights.length ? insights : defaults).map(value => el('li', '', value)));
      renderItemTable(map);
      renderSources(map);
      renderCandidates(map);
    }

    function renderItemTable(map) {
      const wrap = byId('item-table-wrap');
      const table = el('table');
      const caption = el('caption', '', '국회확정 목·세목과 집행채널');
      const head = document.createElement('thead');
      const headRow = document.createElement('tr');
      ['목', '세목', '집행채널', '금액', '비중'].forEach(value => headRow.append(el('th', '', value)));
      head.append(headRow);
      const body = document.createElement('tbody');
      const channelByCode = new Map(array(map.channels).map(row => [row.code, row.label]));
      array(map.budget_items).forEach(row => {
        const tr = document.createElement('tr');
        tr.append(
          el('td', '', row.mok_name),
          el('td', '', row.semok_name),
          el('td', '', channelByCode.get(row.channel_code) || '기타'),
          el('td', 'amount', won(row.amount_won, true)),
          el('td', 'amount', percent(row.amount_won, object(map.core).congress_amt)),
        );
        body.append(tr);
      });
      table.append(caption, head, body);
      wrap.replaceChildren(table);
    }

    function renderSources(map) {
      const target = byId('source-list');
      target.replaceChildren();
      const api = el('div', 'source-row');
      api.append(el('strong', '', 'Open Fiscal · ExpenditureBudgetAdd2'), el('span', '', '금액 필드 Y_YY_DFN_KCUR_AMT · 국회확정액과 목·세목'));
      target.append(api);
      array(map.evidence).forEach(row => {
        const source = el('div', 'source-row');
        const pages = row.page_start ? `p.${row.page_start}${row.page_end && row.page_end !== row.page_start ? `–${row.page_end}` : ''}` : '페이지 미상';
        source.append(
          el('strong', '', row.label),
          el('span', '', `${row.source_pdf || '부처 사업설명자료'} · ${pages}`),
          el('span', '', `${row.chunk_start || ''}${row.chunk_end && row.chunk_end !== row.chunk_start ? `–${row.chunk_end}` : ''}`),
        );
        target.append(source);
      });
      const local = object(map.local_summary);
      if (number(local.candidate_count)) {
        const source = el('div', 'source-row');
        const scope = number(object(local.match_scopes).pdf_subproject_keyword)
          ? `PDF 내역사업 키워드 ${number(object(local.match_scopes).pdf_subproject_keyword)}건 포함`
          : '중앙 세부사업명 키워드';
        source.append(
          el('strong', '', 'LOFIN · QWGJK 세부사업별 세출현황'),
          el('span', '', `${dateLabel(array(local.snapshot_dates)[0])} 기준 · ${scope}`),
          el('span', '', '예산현액·국비·시도비·시군구비·기타·지출액·편성액'),
        );
        target.append(source);
      }
      const warnings = array(map.warnings);
      const warningList = byId('warning-list');
      warningList.hidden = !warnings.length;
      warningList.replaceChildren(...warnings.map(value => el('li', '', value)));
    }

    function fundingCell(row) {
      const cell = el('td', 'funding-cell');
      const components = fundingComponents(row);
      const total = components.reduce((sum, component) => sum + component.amount_won, 0);
      const track = el('div', 'funding-track');
      track.setAttribute('aria-label', components.map(component => `${component.label} ${won(component.amount_won, true)}`).join(', '));
      components.forEach(component => {
        const segment = el('span', `funding-${component.kind}`);
        segment.style.width = `${total ? component.amount_won * 100 / total : 0}%`;
        track.append(segment);
      });
      const labels = components.map(component => `${component.label} ${won(component.amount_won)}`).join(' · ');
      cell.append(track, el('div', 'funding-text', labels || '재원구성 0원'));
      return cell;
    }

    function alignmentLabel(value) {
      return ({
        exact_title: '지방사업명 정확일치',
        title_overlap: '사업명 포함일치',
        keyword_contained: '검색어 포함',
        query_result: '검색 결과',
      })[value] || '검색 결과';
    }

    function renderCandidates(map) {
      const wrap = byId('candidate-table-wrap');
      const rows = array(map.local_candidates);
      const summary = object(map.local_summary);
      if (!rows.length) {
        wrap.replaceChildren(el('p', 'candidate-note', 'LOFIN에서 양수 국비 지역사업 후보를 확인하지 못했습니다. 지역명과 집행액을 추정하지 않았습니다.'));
        return;
      }
      const overview = el('div', 'local-overview');
      [
        ['지역 관측 범위', `${number(summary.candidate_count)}건 · ${number(summary.unique_local_gov_count)}개 지자체`],
        ['행정 단계', `광역 ${number(summary.wide_area_row_count)} · 기초 ${number(summary.basic_row_count)}`],
        ['조회·집행', `${dateLabel(array(summary.snapshot_dates)[0])} · 관측 ${rateLabel(summary.observed_execution_rate)}`],
      ].forEach(([label, value]) => {
        const stat = el('div', 'local-stat');
        stat.append(el('span', '', label), el('strong', '', value));
        overview.append(stat);
      });
      const tableWrap = el('div', 'table-wrap');
      const table = el('table');
      const caption = el('caption', '', `LOFIN 지역 예산 편성·지출 ${rows.length}/${number(summary.candidate_count)}건 · 국비 관측액순 · 비가산`);
      const head = document.createElement('thead');
      const hr = document.createElement('tr');
      ['지역', '지방 세부사업', '재원 구성', '예산현액', '지출액', '집행률', '연결 근거'].forEach(value => hr.append(el('th', '', value)));
      head.append(hr);
      const body = document.createElement('tbody');
      rows.forEach(row => {
        const tr = document.createElement('tr');
        const basis = row.match_scope === 'pdf_subproject_keyword'
          ? `PDF 내역 ‘${row.matched_subproject_name || row.keyword}’`
          : `중앙 사업명 ‘${row.keyword || map.title}’`;
        const detail = el('td');
        detail.append(
          el('strong', '', row.detail_business_name || '지방 세부사업명 미상'),
          el('div', 'match-text', `${row.account_name || '회계 미상'} · ${row.field_name || '분야 미상'} · ${row.section_name || '부문 미상'}`),
          el('div', 'match-text', row.detail_business_code || '사업코드 미상'),
        );
        const match = el('td');
        match.append(el('span', '', basis), el('div', 'match-text', `${alignmentLabel(row.name_alignment)} · keyword_candidate`));
        tr.append(
          el('td', '', `${row.local_gov_name}${row.local_level ? ` · ${row.local_level}` : ''}`),
          detail,
          fundingCell(row),
          el('td', 'amount', won(row.budget_cash_amt, true)),
          el('td', 'amount', won(row.spend_amt, true)),
          el('td', 'amount', rateLabel(row.execution_rate)),
          match,
        );
        body.append(tr);
      });
      table.append(caption, head, body);
      tableWrap.append(table);
      const note = el('p', 'candidate-note', '예산현액·재원구성·지출액은 지방재정365 조회일 스냅샷입니다. 광역·기초 행에 같은 국비가 중복될 수 있고 중앙사업과의 교부 관계는 명칭 기반 후보이므로 관측합을 중앙 확정액과 합산·대사하지 않습니다.');
      wrap.replaceChildren(overview, tableWrap, note);
    }

    function searchTerms(map) {
      const core = object(map.core);
      const localTerms = array(map.local_candidates).flatMap(row => [row.region_name, row.local_gov_name, row.detail_business_name]);
      return normalize([map.title, core.office_name, core.account_name, core.field_name, core.section_name, core.program_name, core.unit_business_name, ...localTerms].join(' '));
    }
    const SEARCH_INDEX = MAPS.map(map => ({ map, key: searchTerms(map) }));

    function updateSearch() {
      const input = byId('business-search');
      const results = byId('search-results');
      const query = normalize(input.value);
      const rows = (query
        ? SEARCH_INDEX.filter(row => row.key.includes(query))
        : SEARCH_INDEX.slice(0, 10)
      ).slice(0, 10).map(row => row.map);
      state.searchRows = rows;
      state.searchIndex = -1;
      results.replaceChildren();
      rows.forEach((map, index) => {
        const core = object(map.core);
        const button = el('button', 'result-button');
        button.type = 'button';
        button.role = 'option';
        button.dataset.resultIndex = String(index);
        button.setAttribute('aria-selected', 'false');
        button.append(
          el('span', 'result-title', map.title),
          el('span', 'result-meta', `${core.office_name} · ${core.account_name} · ${core.program_name}${number(map.local_candidate_total_count) ? ` · 지역관측 ${number(map.local_candidate_total_count)}건` : ''}`),
          el('span', 'result-amount', won(core.congress_amt, true)),
        );
        results.append(button);
      });
      if (!rows.length) results.append(el('div', 'result-button', '검색 결과가 없습니다.'));
      results.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    }

    function chooseSearch(index) {
      const map = state.searchRows[index];
      if (!map) return;
      const input = byId('business-search');
      input.value = map.title;
      hideSearch();
      renderMap(map);
      const url = new URL(window.location.href);
      url.searchParams.set('business', map.id);
      window.history.replaceState({}, '', url);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function hideSearch() {
      byId('search-results').hidden = true;
      byId('business-search').setAttribute('aria-expanded', 'false');
      state.searchIndex = -1;
    }

    byId('stages').addEventListener('click', event => {
      const target = event.target.closest('[data-node-id]');
      if (target) selectNode(target.dataset.nodeId);
    });
    byId('business-search').addEventListener('input', updateSearch);
    byId('business-search').addEventListener('focus', updateSearch);
    byId('business-search').addEventListener('keydown', event => {
      if (event.key === 'Escape') { hideSearch(); return; }
      if (!['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key)) return;
      event.preventDefault();
      if (event.key === 'ArrowDown') state.searchIndex = Math.min(state.searchRows.length - 1, state.searchIndex + 1);
      if (event.key === 'ArrowUp') state.searchIndex = Math.max(0, state.searchIndex - 1);
      if (event.key === 'Enter') { chooseSearch(state.searchIndex >= 0 ? state.searchIndex : 0); return; }
      document.querySelectorAll('.result-button[role="option"]').forEach((node, index) => {
        node.setAttribute('aria-selected', index === state.searchIndex ? 'true' : 'false');
      });
    });
    byId('search-results').addEventListener('mousedown', event => {
      const target = event.target.closest('[data-result-index]');
      if (target) { event.preventDefault(); chooseSearch(number(target.dataset.resultIndex)); }
    });
    document.addEventListener('click', event => {
      if (!event.target.closest('.search-shell')) hideSearch();
    });
    byId('print-button').addEventListener('click', () => window.print());

    let resizeFrame = 0;
    const scheduleDraw = () => {
      cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(drawEdges);
    };
    window.addEventListener('resize', scheduleDraw, { passive: true });
    if ('ResizeObserver' in window) new ResizeObserver(scheduleDraw).observe(byId('board'));

    const requestedId = new URLSearchParams(window.location.search).get('business');
    const initial = BY_ID.get(requestedId) || BY_ID.get(String(META.default_business_id)) || MAPS[0];
    if (initial) {
      byId('business-search').value = initial.title;
      renderMap(initial);
    }
  </script>
</body>
</html>
'''


def main() -> int:
    payload = load_payload(SOURCE)
    year = int((payload.get("meta") or {}).get("year") or 2026)
    html_text = (
        HTML_TEMPLATE.replace("__YEAR__", str(year))
        .replace("__PAYLOAD__", safe_json_for_html(payload))
    )
    for destination in (OUT, OUT_YEAR):
        with destination.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(html_text)
    print(
        json.dumps(
            {
                "output": str(OUT),
                "year_alias": str(OUT_YEAR),
                "bytes": len(html_text.encode("utf-8")),
                "map_count": len(payload["maps"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
