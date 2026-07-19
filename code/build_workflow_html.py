#!/usr/bin/env python3
"""Build a standalone, evidence-aware workflow explorer for one business at a time.

The embedded data is produced by ``build_business_workflows.py``.  The browser
creates DOM nodes only for the currently selected business; the remaining
records stay in the inert JSON payload and the lightweight search index.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "normalized" / "business_workflows_2026_pilots.json"
OUT = ROOT / "artifacts" / "detailed_business_workflows.html"


def load_payload(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(
            f"missing workflow dataset: {path}\n"
            "run `python3 code/build_business_workflows.py` first"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid workflow JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"expected a JSON object in {path}")
    return value


def validate_payload(payload: dict) -> tuple[list[dict], int]:
    workflows = payload.get("workflows")
    if not isinstance(workflows, list) or not workflows:
        raise SystemExit(f"workflow dataset has no non-empty workflows list: {SOURCE}")

    seen_businesses: set[str] = set()
    for position, workflow in enumerate(workflows):
        if not isinstance(workflow, dict):
            raise SystemExit(f"workflow #{position} is not an object")
        business_id = workflow.get("id")
        if not isinstance(business_id, str) or not business_id:
            raise SystemExit(f"workflow #{position} has no id")
        if business_id in seen_businesses:
            raise SystemExit(f"duplicate workflow id: {business_id}")
        seen_businesses.add(business_id)

        for field in (
            "actors",
            "phases",
            "nodes",
            "edges",
            "execution_channels",
            "budget_breakdown",
            "local_reflections",
            "evidence_sections",
            "pdf_cards",
        ):
            if not isinstance(workflow.get(field), list):
                raise SystemExit(f"{business_id}: expected list field {field}")

        node_ids = {node.get("id") for node in workflow["nodes"] if isinstance(node, dict)}
        if None in node_ids or len(node_ids) != len(workflow["nodes"]):
            raise SystemExit(f"{business_id}: node ids are missing or duplicated")
        for edge in workflow["edges"]:
            if not isinstance(edge, dict):
                raise SystemExit(f"{business_id}: edge is not an object")
            if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
                raise SystemExit(f"{business_id}: edge endpoint does not exist: {edge.get('id')}")

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    try:
        year = int(meta.get("year"))
    except (TypeError, ValueError):
        first_core = workflows[0].get("core") if isinstance(workflows[0].get("core"), dict) else {}
        try:
            year = int(first_core.get("year"))
        except (TypeError, ValueError):
            match = re.search(r"(?:19|20)\d{2}", SOURCE.name)
            year = int(match.group()) if match else 2026

    default_id = meta.get("default_business_id")
    if default_id and default_id not in seen_businesses:
        raise SystemExit(f"meta.default_business_id does not exist: {default_id}")
    return workflows, year


def safe_json_for_html(value: object) -> str:
    """Serialize JSON without allowing source text to close its script tag."""

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


HTML_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="light dark" />
  <title>Koreabudget100 · __YEAR__ 세부사업 상세 체계도</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #f4f7f5;
      --surface: #ffffff;
      --surface-2: #f6faf8;
      --surface-3: #eaf3ef;
      --ink: #17231e;
      --muted: #64726c;
      --line: #cbd8d2;
      --line-strong: #96aaa1;
      --brand-950: #041d14;
      --brand-900: #06291d;
      --brand-800: #08442f;
      --brand-700: #096044;
      --brand-600: #0b7b57;
      --brand-100: #ddf2e9;
      --blue: #3568b5;
      --blue-soft: #e6eef9;
      --teal: #087c80;
      --teal-soft: #ddf2f2;
      --amber: #9c5d08;
      --amber-soft: #fff0d2;
      --violet: #6f55a2;
      --violet-soft: #f0eafb;
      --danger: #9f3b36;
      --danger-soft: #fbe9e7;
      --shadow: 0 9px 24px rgba(18, 50, 38, .09);
      --radius: 14px;
      --stage-width: 144px;
      --lane-width: 250px;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #09110e;
        --surface: #111c18;
        --surface-2: #15241e;
        --surface-3: #1a3027;
        --ink: #edf6f1;
        --muted: #a8b9b1;
        --line: #30463d;
        --line-strong: #526c61;
        --brand-100: #163c2d;
        --blue-soft: #182b46;
        --teal-soft: #133a3b;
        --amber-soft: #3c2c12;
        --violet-soft: #2a223b;
        --danger-soft: #3d201f;
        --shadow: 0 10px 28px rgba(0, 0, 0, .26);
      }
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--bg);
      font-family: Pretendard, "Noto Sans KR", -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
      line-height: 1.5;
    }
    button, input, select { font: inherit; }
    button { cursor: pointer; }
    button:focus-visible, input:focus-visible, select:focus-visible,
    [tabindex]:focus-visible {
      outline: 3px solid #58a9ff;
      outline-offset: 2px;
    }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .hero {
      color: #f6fff9;
      background:
        radial-gradient(900px 340px at 95% -20%, rgba(30, 154, 105, .34), transparent 70%),
        linear-gradient(135deg, var(--brand-950), var(--brand-900));
      border-top: 7px solid #20a774;
      padding: 18px max(22px, calc((100vw - 1760px) / 2)) 20px;
    }
    .hero-top {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      font-size: 12px;
      color: #b8d4c8;
    }
    .brand { color: white; font-weight: 800; letter-spacing: -.02em; }
    .brand span { color: #4cd49e; }
    .hero-title-row {
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 24px;
      margin-top: 18px;
    }
    .hero-main { min-width: 0; }
    .eyebrow {
      margin-bottom: 4px;
      color: #91cbb4;
      font-size: 12px;
      font-weight: 750;
      letter-spacing: .03em;
    }
    h1 {
      margin: 0;
      max-width: 1100px;
      font-size: clamp(25px, 3vw, 42px);
      line-height: 1.16;
      letter-spacing: -.035em;
      overflow-wrap: anywhere;
    }
    .hero-summary { margin: 9px 0 0; max-width: 1050px; color: #c7ddd4; font-size: 13px; }
    .coverage-mark {
      flex: 0 0 auto;
      min-width: 180px;
      padding: 11px 14px;
      border: 1px solid rgba(119, 220, 177, .34);
      border-radius: 12px;
      background: rgba(13, 73, 52, .64);
      font-size: 12px;
    }
    .coverage-mark b { display: block; margin-top: 2px; color: white; font-size: 15px; }
    .breadcrumb { margin-top: 15px; }
    .breadcrumb ol {
      display: flex;
      flex-wrap: wrap;
      gap: 4px 0;
      margin: 0;
      padding: 0;
      list-style: none;
      color: #bcd3ca;
      font-size: 11px;
    }
    .breadcrumb li { min-width: 0; overflow-wrap: anywhere; }
    .breadcrumb li:not(:last-child)::after { content: "›"; padding: 0 7px; color: #668f7e; }
    .hero-metrics {
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 8px;
      margin-top: 16px;
    }
    .hero-metric {
      padding: 9px 11px;
      border: 1px solid rgba(157, 205, 184, .2);
      border-radius: 10px;
      background: rgba(255, 255, 255, .045);
    }
    .hero-metric span { display: block; color: #9fc4b5; font-size: 10px; }
    .hero-metric strong { display: block; margin-top: 1px; color: white; font-size: 14px; overflow-wrap: anywhere; }
    .control-shell {
      position: sticky;
      top: 0;
      z-index: 30;
      border-bottom: 1px solid var(--line);
      background: color-mix(in srgb, var(--surface) 94%, transparent);
      backdrop-filter: blur(14px);
    }
    .controls {
      display: flex;
      align-items: end;
      gap: 10px;
      max-width: 1760px;
      margin: 0 auto;
      padding: 12px 22px;
    }
    .field { display: grid; gap: 4px; min-width: 0; }
    .field.search { position: relative; flex: 1 1 640px; }
    .field.ministry { flex: 0 1 260px; }
    .field label { color: var(--muted); font-size: 10px; font-weight: 750; }
    input, select {
      width: 100%;
      min-height: 42px;
      border: 1px solid var(--line-strong);
      border-radius: 10px;
      padding: 8px 11px;
      color: var(--ink);
      background: var(--surface);
    }
    .search-results {
      position: absolute;
      top: calc(100% + 7px);
      left: 0;
      right: 0;
      z-index: 60;
      max-height: min(60vh, 520px);
      overflow: auto;
      padding: 6px;
      border: 1px solid var(--line-strong);
      border-radius: 12px;
      background: var(--surface);
      box-shadow: var(--shadow);
    }
    .search-results[hidden] { display: none; }
    .result-button {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 2px 12px;
      width: 100%;
      padding: 9px 10px;
      border: 0;
      border-radius: 8px;
      color: var(--ink);
      background: transparent;
      text-align: left;
    }
    .result-button:hover, .result-button:focus-visible { background: var(--surface-3); }
    .result-button strong { overflow-wrap: anywhere; }
    .result-button span { color: var(--muted); font-size: 11px; }
    .result-empty { padding: 18px; color: var(--muted); text-align: center; font-size: 12px; }
    .tabs {
      display: flex;
      gap: 6px;
      max-width: 1760px;
      margin: 0 auto;
      padding: 10px 22px 0;
    }
    .tab {
      min-height: 42px;
      padding: 8px 15px;
      border: 1px solid transparent;
      border-radius: 10px 10px 0 0;
      color: var(--muted);
      background: transparent;
      font-weight: 750;
    }
    .tab[aria-selected="true"] {
      color: var(--brand-700);
      border-color: var(--line);
      border-bottom-color: var(--surface);
      background: var(--surface);
    }
    main { max-width: 1760px; margin: 0 auto; padding: 16px 22px 54px; }
    .coverage-banner {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      margin-bottom: 14px;
      padding: 11px 13px;
      border: 1px solid var(--line);
      border-left: 5px solid var(--brand-600);
      border-radius: 10px;
      background: var(--surface);
      font-size: 12px;
    }
    .coverage-banner.structured_facts { border-left-color: var(--amber); }
    .coverage-banner.api_only { border-left-color: var(--line-strong); }
    .coverage-banner strong { white-space: nowrap; }
    .coverage-banner ul { margin: 0; padding-left: 18px; }
    .tab-panel[hidden] { display: none; }
    .panel-card {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface);
      box-shadow: 0 2px 8px rgba(16, 48, 36, .035);
    }
    .section-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 14px;
      margin-bottom: 10px;
    }
    .section-head h2, .section-head h3 { margin: 0; letter-spacing: -.02em; }
    .section-head p { margin: 0; color: var(--muted); font-size: 11px; }
    .workflow-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 340px;
      gap: 14px;
      align-items: start;
    }
    .graph-column { min-width: 0; }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 14px;
      align-items: center;
      margin-bottom: 10px;
      padding: 9px 11px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--surface);
      color: var(--muted);
      font-size: 11px;
    }
    .legend strong { color: var(--ink); }
    .edge-toggle { display: inline-flex; align-items: center; gap: 5px; cursor: pointer; }
    .edge-toggle input { width: 14px; min-height: 14px; margin: 0; }
    .line-swatch { display: inline-block; width: 28px; height: 0; border-top: 2px solid var(--line-strong); }
    .line-swatch.fund { border-color: var(--brand-600); border-top-width: 3px; }
    .line-swatch.delivery { border-color: var(--teal); }
    .line-swatch.context { border-color: var(--violet); border-top-style: dashed; }
    .line-swatch.candidate { border-color: var(--line-strong); border-top-style: dotted; border-top-width: 3px; }
    .matrix-scroll {
      position: relative;
      overflow: auto;
      max-height: calc(100vh - 174px);
      border: 1px solid var(--line-strong);
      border-radius: 12px;
      background: var(--surface);
    }
    .matrix {
      position: relative;
      display: grid;
      min-width: max-content;
      isolation: isolate;
      background: var(--surface);
    }
    .matrix-corner, .actor-head, .stage-head {
      position: sticky;
      z-index: 8;
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      background: var(--surface-2);
    }
    .matrix-corner {
      top: 0;
      left: 0;
      display: grid;
      place-content: center;
      padding: 10px;
      color: var(--muted);
      font-size: 10px;
      text-align: center;
    }
    .actor-head {
      top: 0;
      min-height: 86px;
      padding: 13px 14px 10px;
      border-top: 5px solid var(--brand-600);
    }
    .actor-head:nth-of-type(3n) { border-top-color: var(--blue); }
    .actor-head:nth-of-type(4n) { border-top-color: var(--amber); }
    .actor-head b { display: block; font-size: 13px; overflow-wrap: anywhere; }
    .actor-head span { display: block; margin-top: 3px; color: var(--muted); font-size: 10px; overflow-wrap: anywhere; }
    .stage-head {
      left: 0;
      min-height: 150px;
      padding: 14px 12px;
    }
    .stage-head b { display: block; color: var(--brand-700); font-size: 15px; }
    .stage-head span { display: block; margin-top: 4px; color: var(--muted); font-size: 11px; }
    .matrix-cell {
      position: relative;
      display: flex;
      flex-direction: column;
      justify-content: flex-start;
      gap: 11px;
      min-height: 150px;
      padding: 22px 18px;
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      background: color-mix(in srgb, var(--surface) 96%, var(--brand-100));
    }
    .matrix-cell:nth-child(even) { background: color-mix(in srgb, var(--surface) 98%, var(--surface-3)); }
    .edge-layer { position: absolute; inset: 0; z-index: 2; overflow: visible; pointer-events: none; }
    .edge-path {
      fill: none;
      stroke: #52635b;
      stroke-width: 1.6;
      vector-effect: non-scaling-stroke;
      opacity: .78;
    }
    .edge-path.type-fund { stroke: var(--brand-600); stroke-width: 2.6; }
    .edge-path.type-delivery { stroke: var(--teal); stroke-width: 2; }
    .edge-path.type-context { stroke: var(--violet); stroke-dasharray: 7 5; }
    .edge-path.type-candidate { stroke: var(--line-strong); stroke-width: 2.2; stroke-dasharray: 2 7; }
    .edge-path.assertion-derived { stroke-dasharray: 7 5; }
    .edge-path.is-dim { opacity: .08; }
    .edge-path.is-active { opacity: 1; stroke-width: 3.4; }
    .edge-label rect { fill: var(--surface); stroke: var(--line); rx: 5; }
    .edge-label text { fill: var(--muted); font-size: 9px; text-anchor: middle; dominant-baseline: central; }
    .edge-label.is-dim { opacity: .08; }
    .node-card {
      position: relative;
      z-index: 4;
      width: 100%;
      min-width: 210px;
      padding: 10px 11px 11px;
      border: 1px solid var(--line-strong);
      border-left: 5px solid var(--brand-600);
      border-radius: 10px;
      color: var(--ink);
      background: var(--surface);
      box-shadow: 0 3px 8px rgba(20, 45, 35, .10);
      text-align: left;
      transition: opacity .15s, transform .15s, box-shadow .15s;
    }
    .node-card:hover { transform: translateY(-1px); box-shadow: var(--shadow); }
    .node-card.kind-budget, .node-card.kind-budget_item { border-left-color: var(--brand-700); }
    .node-card.kind-procedure { border-left-color: var(--blue); }
    .node-card.kind-local_candidate { border-left-color: var(--line-strong); border-left-style: dotted; }
    .node-card.kind-performance, .node-card.kind-review { border-left-color: var(--amber); }
    .node-card.kind-basis { border-left-color: var(--violet); }
    .node-card.is-dim { opacity: .18; }
    .node-card.is-path { opacity: 1; box-shadow: 0 0 0 2px color-mix(in srgb, var(--blue) 55%, transparent); }
    .node-card.is-selected { opacity: 1; box-shadow: 0 0 0 3px var(--brand-600), var(--shadow); }
    .node-top { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
    .node-id { color: var(--muted); font: 700 9px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace; }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      max-width: 100%;
      padding: 2px 6px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--muted);
      background: var(--surface-2);
      font-size: 9px;
      font-weight: 700;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }
    .badge.api { color: var(--brand-700); border-color: var(--brand-600); background: var(--brand-100); }
    .badge.documented { color: var(--blue); border-color: var(--blue); background: var(--blue-soft); }
    .badge.candidate { color: var(--muted); border-style: dashed; }
    .badge.derived { color: var(--violet); border-color: var(--violet); background: var(--violet-soft); }
    .node-label {
      display: -webkit-box;
      margin-top: 6px;
      overflow: hidden;
      font-size: 12px;
      font-weight: 760;
      line-height: 1.4;
      overflow-wrap: anywhere;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 4;
    }
    .node-meta { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 7px; }
    .node-amount { display: block; margin-top: 6px; color: var(--brand-700); font-size: 11px; font-weight: 750; }
    .empty-state {
      padding: 34px 24px;
      border: 1px dashed var(--line-strong);
      border-radius: 12px;
      color: var(--muted);
      background: var(--surface);
      text-align: center;
    }
    .empty-state strong { display: block; margin-bottom: 6px; color: var(--ink); font-size: 16px; }
    .node-detail {
      position: sticky;
      top: 118px;
      max-height: calc(100vh - 136px);
      overflow: auto;
      padding: 14px;
    }
    .node-detail h2 { margin: 0; font-size: 16px; letter-spacing: -.02em; overflow-wrap: anywhere; }
    .node-detail .detail-copy { margin: 10px 0 0; white-space: pre-wrap; font-size: 12px; overflow-wrap: anywhere; }
    .detail-section { margin-top: 15px; padding-top: 12px; border-top: 1px solid var(--line); }
    .detail-section h3 { margin: 0 0 7px; font-size: 12px; }
    .kv { display: grid; grid-template-columns: 86px minmax(0, 1fr); gap: 5px 8px; margin: 8px 0 0; font-size: 11px; }
    .kv dt { color: var(--muted); }
    .kv dd { margin: 0; overflow-wrap: anywhere; }
    .source-ref { margin-top: 7px; padding: 8px; border-radius: 8px; background: var(--surface-2); font-size: 10px; overflow-wrap: anywhere; }
    .relation-fallback { margin-top: 14px; padding: 14px; }
    .relation-fallback ol { margin: 8px 0 0; padding-left: 24px; columns: 2; column-gap: 30px; font-size: 11px; }
    .relation-fallback li { break-inside: avoid; margin: 0 0 7px; }
    .relation-fallback button { padding: 0; border: 0; color: var(--blue); background: transparent; text-align: left; text-decoration: underline; text-decoration-style: dotted; }
    .budget-grid { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1.95fr); gap: 14px; }
    .budget-card { padding: 16px; }
    .amount-hero { padding: 16px; border-radius: 12px; color: white; background: linear-gradient(135deg, var(--brand-800), var(--brand-600)); }
    .amount-hero span { display: block; color: #c2e2d5; font-size: 11px; }
    .amount-hero strong { display: block; margin-top: 4px; font-size: 24px; letter-spacing: -.03em; }
    .flow-arrow { margin: 10px 0; color: var(--muted); font-size: 11px; text-align: center; }
    .channel-stack { display: grid; gap: 8px; }
    .channel-card { padding: 10px 11px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface-2); }
    .channel-title { display: flex; justify-content: space-between; gap: 10px; font-size: 12px; }
    .channel-title b:last-child { color: var(--brand-700); }
    .share-track { height: 5px; margin-top: 8px; overflow: hidden; border-radius: 99px; background: var(--line); }
    .share-bar { height: 100%; background: var(--brand-600); }
    .channel-card small { display: block; margin-top: 6px; color: var(--muted); }
    .candidate-bridge {
      margin-top: 13px;
      padding: 11px;
      border: 2px dotted var(--line-strong);
      border-radius: 10px;
      color: var(--muted);
      background: var(--surface-2);
      font-size: 11px;
    }
    .warning-box {
      margin-top: 10px;
      padding: 10px 11px;
      border: 1px solid #d3a35f;
      border-radius: 9px;
      color: var(--amber);
      background: var(--amber-soft);
      font-size: 11px;
    }
    .table-wrap { overflow: auto; border: 1px solid var(--line); border-radius: 10px; }
    table { width: 100%; border-collapse: collapse; font-size: 11px; }
    th, td { padding: 8px 9px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; overflow-wrap: anywhere; }
    th { position: sticky; top: 0; z-index: 1; color: var(--muted); background: var(--surface-2); font-size: 10px; white-space: nowrap; }
    td.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
    tr:last-child td { border-bottom: 0; }
    .subsection { margin-top: 14px; padding: 16px; }
    .subsection:first-child { margin-top: 0; }
    .evidence-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .coverage-card { padding: 13px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface-2); }
    .coverage-card span { color: var(--muted); font-size: 10px; }
    .coverage-card strong { display: block; margin-top: 3px; font-size: 15px; }
    .coverage-card p { margin: 5px 0 0; color: var(--muted); font-size: 11px; }
    .evidence-list { display: grid; gap: 8px; }
    details.evidence-item { border: 1px solid var(--line); border-radius: 9px; background: var(--surface); }
    details.evidence-item summary { display: flex; justify-content: space-between; gap: 12px; padding: 10px 11px; cursor: pointer; font-size: 12px; font-weight: 700; }
    details.evidence-item summary span:last-child { color: var(--muted); font-size: 10px; font-weight: 500; }
    .evidence-body { padding: 0 11px 11px; border-top: 1px solid var(--line); }
    .evidence-text { margin: 9px 0 0; white-space: pre-wrap; font: inherit; font-size: 11px; line-height: 1.65; overflow-wrap: anywhere; }
    .pdf-card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 8px; }
    .pdf-card { padding: 11px; border: 1px solid var(--line); border-radius: 9px; background: var(--surface-2); }
    .pdf-card strong { display: block; font-size: 12px; overflow-wrap: anywhere; }
    .interpretation-list { margin: 0; padding-left: 18px; font-size: 11px; }
    .interpretation-list li + li { margin-top: 5px; }
    .muted { color: var(--muted); }
    footer { max-width: 1760px; margin: 0 auto; padding: 0 22px 30px; color: var(--muted); font-size: 10px; }
    @media (max-width: 1100px) {
      .workflow-layout, .budget-grid { grid-template-columns: 1fr; }
      .node-detail { position: static; max-height: none; }
      .hero-metrics { grid-template-columns: repeat(3, 1fr); }
      .evidence-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 760px) {
      .hero { padding-inline: 15px; }
      .hero-title-row { display: block; }
      .coverage-mark { margin-top: 14px; }
      .hero-metrics { grid-template-columns: repeat(2, 1fr); }
      .controls { display: grid; grid-template-columns: 1fr; padding-inline: 14px; }
      .tabs { overflow-x: auto; padding-inline: 14px; }
      main { padding-inline: 14px; }
      .coverage-banner { display: block; }
      .matrix-scroll { max-height: none; overflow: visible; border: 0; background: transparent; }
      .matrix { display: block; min-width: 0; background: transparent; }
      .matrix-corner, .actor-head, .edge-layer { display: none; }
      .stage-head { position: static; min-height: 0; margin-top: 14px; padding: 10px 11px; border: 1px solid var(--line); border-radius: 9px 9px 0 0; }
      .matrix-cell { min-height: 0; padding: 12px; border: 1px solid var(--line); border-top: 0; }
      .matrix-cell:empty { display: none; }
      .matrix-cell::before { content: attr(data-actor-label); color: var(--muted); font-size: 10px; font-weight: 750; }
      .node-card { min-width: 0; }
      .relation-fallback ol { columns: 1; }
      .section-head { display: block; }
      .section-head p { margin-top: 3px; }
    }
    @page { size: A3 landscape; margin: 8mm; }
    @media print {
      :root {
        --bg: #fff;
        --surface: #fff;
        --surface-2: #f5f7f6;
        --surface-3: #eef3f0;
        --ink: #111;
        --muted: #4e5854;
        --line: #aeb9b4;
        --line-strong: #7e8d86;
        --shadow: none;
      }
      html, body { background: white; }
      body { font-size: 8pt; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
      .hero { padding: 4mm 6mm; border-top-width: 3px; }
      .hero-title-row { margin-top: 3mm; }
      h1 { font-size: 20pt; }
      .hero-summary, .breadcrumb { font-size: 7pt; }
      .hero-metrics { margin-top: 3mm; gap: 2mm; }
      .control-shell, .screen-only { display: none !important; }
      main { max-width: none; padding: 4mm 0; }
      .coverage-banner { margin-bottom: 3mm; }
      .workflow-layout { grid-template-columns: minmax(0, 1fr) 74mm; gap: 3mm; }
      .matrix-scroll { max-height: none; overflow: visible; }
      .matrix { min-width: 0; grid-template-columns: 30mm repeat(var(--print-lanes), minmax(44mm, 1fr)) !important; }
      .actor-head { min-height: 17mm; }
      .stage-head, .matrix-cell { min-height: 32mm; }
      .matrix-cell { padding: 4mm 3mm; }
      .node-card { min-width: 0; padding: 2mm; break-inside: avoid; }
      .node-label { font-size: 7pt; -webkit-line-clamp: 6; }
      .node-detail { position: static; max-height: none; padding: 3mm; }
      .relation-fallback { break-before: page; }
      .relation-fallback ol { columns: 3; }
      .panel-card, .node-card, details.evidence-item { box-shadow: none; }
      footer { max-width: none; padding: 0; }
    }
  </style>
</head>
<body>
  <header class="hero">
    <div class="hero-top">
      <div class="brand">Koreabudget<span>100</span> · 세부사업 상세 체계도</div>
      <div>기준연도 __YEAR__ · 열린재정 API / 설명자료 PDF / LOFIN QWGJK</div>
    </div>
    <div class="hero-title-row">
      <div class="hero-main">
        <div class="eyebrow" id="business-number">사업 선택 중</div>
        <h1 id="business-title">세부사업 상세 체계도</h1>
        <p class="hero-summary" id="business-summary"></p>
      </div>
      <div class="coverage-mark">
        데이터 커버리지
        <b id="coverage-mark">확인 중</b>
      </div>
    </div>
    <nav class="breadcrumb" aria-label="예산 분류 경로"><ol id="breadcrumb"></ol></nav>
    <div class="hero-metrics" id="hero-metrics" aria-live="polite"></div>
  </header>

  <div class="control-shell screen-only">
    <div class="controls">
      <div class="field search">
        <label for="business-search">세부사업 검색</label>
        <input id="business-search" type="search" autocomplete="off"
          placeholder="사업명 · 사업코드 · 시행주체 · 지자체 검색" aria-controls="search-results" />
        <div id="search-results" class="search-results" role="listbox" hidden></div>
      </div>
      <div class="field ministry">
        <label for="ministry-filter">부처 필터</label>
        <select id="ministry-filter"><option value="">전체 부처</option></select>
      </div>
    </div>
    <nav class="tabs" role="tablist" aria-label="상세 체계도 보기">
      <button class="tab" id="tab-button-workflow" type="button" role="tab"
        aria-selected="true" aria-controls="tab-workflow" data-tab="workflow">업무 체계도</button>
      <button class="tab" id="tab-button-budget" type="button" role="tab"
        aria-selected="false" aria-controls="tab-budget" data-tab="budget" tabindex="-1">예산·지역 흐름</button>
      <button class="tab" id="tab-button-evidence" type="button" role="tab"
        aria-selected="false" aria-controls="tab-evidence" data-tab="evidence" tabindex="-1">근거·검증</button>
    </nav>
  </div>

  <main>
    <section id="coverage-banner" class="coverage-banner" aria-live="polite"></section>

    <section id="tab-workflow" class="tab-panel" role="tabpanel" aria-labelledby="tab-button-workflow">
      <div class="workflow-layout">
        <div class="graph-column">
          <div class="section-head">
            <h2>단계 × 행위자 업무 체계도</h2>
            <p>노드를 선택하면 모든 선행·후행 경로와 개별 근거가 강조됩니다.</p>
          </div>
          <div id="edge-legend" class="legend screen-only" aria-label="관계선 범례"></div>
          <div id="workflow-empty" hidden></div>
          <div id="matrix-scroll" class="matrix-scroll">
            <div id="matrix" class="matrix" aria-label="업무 단계와 행위자 스윔레인"></div>
          </div>
          <section class="panel-card relation-fallback">
            <div class="section-head">
              <h3>관계 순서 목록</h3>
              <p>SVG 연결선을 보기 어려운 환경을 위한 동일 정보입니다.</p>
            </div>
            <ol id="relation-list"></ol>
          </section>
        </div>
        <aside id="node-detail" class="panel-card node-detail" aria-live="polite">
          <h2>노드 근거</h2>
          <p class="muted">체계도의 노드를 선택하면 내용, 선행·후행 관계, PDF 쪽·청크와 API 필드를 확인할 수 있습니다.</p>
        </aside>
      </div>
    </section>

    <section id="tab-budget" class="tab-panel" role="tabpanel" aria-labelledby="tab-button-budget" hidden>
      <div id="budget-content"></div>
    </section>

    <section id="tab-evidence" class="tab-panel" role="tabpanel" aria-labelledby="tab-button-evidence" hidden>
      <div id="evidence-content"></div>
    </section>
  </main>

  <footer>
    Koreabudget100 · 현재 선택한 세부사업 하나만 화면과 인쇄물에 렌더링합니다. ·
    데이터: <code>__SOURCE__</code> · 외부 네트워크·CDN 미사용 ·
    G0–G6는 읽기 위한 표시 분류이며 원문 자체의 단계 명칭이 아닙니다.
  </footer>

  <script id="workflow-data" type="application/json">__PAYLOAD__</script>
  <script>
    'use strict';

    const DATA = JSON.parse(document.getElementById('workflow-data').textContent);
    const WORKFLOWS = Array.isArray(DATA.workflows) ? DATA.workflows : [];
    const META = DATA.meta || {};
    const SVG_NS = 'http://www.w3.org/2000/svg';
    const EDGE_INFO = {
      sequence: { label: '절차 순서', className: 'sequence' },
      fund: { label: '목·세목 예산 구성', className: 'fund' },
      delivery: { label: '문서상 전달·수혜 관계', className: 'delivery' },
      context: { label: '표시용 분류 관계', className: 'context' },
      candidate: { label: 'LOFIN 키워드 후보', className: 'candidate' },
    };
    const COVERAGE_INFO = {
      documented_flow: { label: 'PDF 명시 절차', description: '설명자료에서 다단계 순서가 확인된 사업입니다.' },
      structured_facts: { label: '구조화 사실', description: '설명자료의 사실은 있으나 명시적 다단계 순서가 부족합니다.' },
      api_only: { label: 'API 정본만', description: 'PDF 확정 매칭이 없어 실제 업무 절차를 표시하지 않습니다.' },
    };
    const ASSERTION_INFO = {
      api: { label: 'API 정본', className: 'api' },
      documented: { label: 'PDF 문서 확인', className: 'documented' },
      candidate: { label: '후보 관계', className: 'candidate' },
      derived: { label: '표시용 파생', className: 'derived' },
    };

    const state = {
      workflow: null,
      selectedNodeId: null,
      hiddenEdgeTypes: new Set(),
      activeTab: 'workflow',
      searchTimer: null,
      resizeObserver: null,
    };

    const byId = (id) => document.getElementById(id);
    const array = (value) => Array.isArray(value) ? value : [];
    const object = (value) => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    const number = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
    const text = (value, fallback = '—') => value == null || value === '' ? fallback : String(value);
    const normalized = (value) => text(value, '').normalize('NFKC').toLocaleLowerCase('ko-KR');
    const won = (value) => Math.round(number(value)).toLocaleString('ko-KR') + '원';
    const compactWon = (value) => {
      const amount = number(value);
      if (Math.abs(amount) >= 1e12) return (amount / 1e12).toFixed(2).replace(/\.00$/, '') + '조원';
      if (Math.abs(amount) >= 1e8) return (amount / 1e8).toFixed(2).replace(/\.00$/, '') + '억원';
      if (Math.abs(amount) >= 1e4) return (amount / 1e4).toFixed(1).replace(/\.0$/, '') + '만원';
      return won(amount);
    };
    const percent = (value) => (number(value) * 100).toFixed(1) + '%';
    const pages = (start, end) => {
      if (start == null) return '쪽 미상';
      return end != null && Number(end) !== Number(start) ? `${start}–${end}쪽` : `${start}쪽`;
    };
    const formatDate = (value) => {
      const raw = text(value, '');
      return /^\d{8}$/.test(raw) ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}` : text(value);
    };

    function el(tag, className, value) {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (value != null) node.textContent = String(value);
      return node;
    }

    function svgEl(tag, attrs = {}) {
      const node = document.createElementNS(SVG_NS, tag);
      Object.entries(attrs).forEach(([name, value]) => node.setAttribute(name, String(value)));
      return node;
    }

    function badge(assertion, overrideLabel) {
      const info = ASSERTION_INFO[assertion] || { label: text(assertion, '근거 미상'), className: '' };
      return el('span', `badge ${info.className}`, overrideLabel || info.label);
    }

    function addKeyValues(parent, rows) {
      const dl = el('dl', 'kv');
      rows.forEach(([label, value]) => {
        if (value == null || value === '' || (Array.isArray(value) && !value.length)) return;
        dl.append(el('dt', '', label), el('dd', '', Array.isArray(value) ? value.join(' · ') : String(value)));
      });
      parent.appendChild(dl);
      return dl;
    }

    function sourceRefText(ref) {
      const source = ref.source_type || ref.source || 'source';
      if (source === 'openfiscal_api') {
        return [
          `열린재정 ${text(ref.service, 'ExpenditureBudgetAdd2')}`,
          ref.field ? `필드 ${ref.field}` : null,
          ref.year ? `기준연도 ${ref.year}` : null,
        ].filter(Boolean).join(' · ');
      }
      if (source === 'ministry_pdf') {
        return [
          text(ref.source_pdf, '설명자료 PDF'),
          pages(ref.page_start, ref.page_end),
          ref.chunk_start ? `청크 ${ref.chunk_start}${ref.chunk_end && ref.chunk_end !== ref.chunk_start ? `–${ref.chunk_end}` : ''}` : null,
          ref.evidence_id ? `근거 ${ref.evidence_id}` : null,
          ref.field ? `구조화 필드 ${ref.field}` : null,
        ].filter(Boolean).join(' · ');
      }
      if (source === 'lofin_api') {
        return [
          `LOFIN ${text(ref.service, 'QWGJK')}`,
          ref.exe_ymd ? `기준일 ${formatDate(ref.exe_ymd)}` : null,
          text(ref.match_status, 'keyword_candidate'),
        ].filter(Boolean).join(' · ');
      }
      return Object.entries(ref).map(([key, value]) => `${key}: ${text(value)}`).join(' · ');
    }

    function corePath(workflow) {
      const core = object(workflow.core);
      return [
        core.year,
        core.office_name,
        core.account_name,
        core.field_name,
        core.section_name,
        core.program_name,
        core.unit_business_name,
        core.detail_business_name || workflow.title,
      ].filter((value) => value != null && value !== '');
    }

    function searchTerms(workflow) {
      const core = object(workflow.core);
      const terms = [workflow.id, workflow.title, ...Object.values(core), ...array(workflow.canonical_key)];
      array(workflow.actors).forEach((actor) => terms.push(actor.name, actor.role));
      array(workflow.pdf_cards).forEach((card) => terms.push(card.clean_title, card.code_hint, card.source_pdf));
      array(workflow.local_reflections).forEach((row) => {
        terms.push(row.local_gov_name, row.detail_business_name, row.detail_business_code, row.keyword);
      });
      return normalized(terms.filter(Boolean).join(' '));
    }

    const SEARCH_INDEX = WORKFLOWS.map((workflow, index) => ({
      workflow,
      index,
      ministry: text(object(workflow.core).office_name, ''),
      haystack: searchTerms(workflow),
    }));

    function setupMinistries() {
      const select = byId('ministry-filter');
      const ministries = [...new Set(SEARCH_INDEX.map((row) => row.ministry).filter(Boolean))]
        .sort((a, b) => a.localeCompare(b, 'ko'));
      ministries.forEach((ministry) => {
        const option = el('option', '', ministry);
        option.value = ministry;
        select.appendChild(option);
      });
    }

    function coverageInfo(workflow) {
      const coverage = object(workflow.coverage);
      return COVERAGE_INFO[coverage.level] || { label: text(coverage.level, '미분류'), description: '커버리지 정보를 확인하세요.' };
    }

    function renderHeader(workflow) {
      const core = object(workflow.core);
      const coverage = object(workflow.coverage);
      const info = coverageInfo(workflow);
      const position = WORKFLOWS.findIndex((item) => item.id === workflow.id) + 1;
      byId('business-number').textContent = `NO ${position.toLocaleString('ko-KR')} · ${text(workflow.id)}`;
      byId('business-title').textContent = text(workflow.title, '이름 없는 세부사업');
      byId('business-summary').textContent =
        '열린재정 국회확정액을 정본으로 하고, 설명자료의 명시 사실·절차와 LOFIN 키워드 후보를 주장 강도별로 분리한 상세 체계도입니다.';
      byId('coverage-mark').textContent = info.label;

      const breadcrumb = byId('breadcrumb');
      breadcrumb.replaceChildren();
      corePath(workflow).forEach((part) => breadcrumb.appendChild(el('li', '', part)));

      const metrics = [
        ['국회확정액', compactWon(core.congress_amt)],
        ['coverage', info.label],
        ['노드', array(workflow.nodes).length.toLocaleString('ko-KR')],
        ['관계', array(workflow.edges).length.toLocaleString('ko-KR')],
        ['행위자 레인', array(workflow.actors).length.toLocaleString('ko-KR')],
      ];
      const box = byId('hero-metrics');
      box.replaceChildren();
      metrics.forEach(([label, value]) => {
        const card = el('div', 'hero-metric');
        card.append(el('span', '', label), el('strong', '', value));
        box.appendChild(card);
      });

      const banner = byId('coverage-banner');
      banner.className = `coverage-banner ${text(coverage.level, '')}`;
      banner.replaceChildren(el('strong', '', `${info.label}:`));
      const list = el('ul');
      list.appendChild(el('li', '', info.description));
      if (coverage.level === 'structured_facts') {
        list.appendChild(el('li', '', '사실 노드는 표시하지만, 원문에 없는 순서 연결·분기·회귀를 만들지 않습니다.'));
      }
      if (coverage.level === 'api_only') {
        list.appendChild(el('li', '', '업무 체계도에는 빈 절차 노드를 채우지 않으며 예산·지역 흐름 탭에서 API 정본만 확인할 수 있습니다.'));
      }
      array(coverage.warnings).forEach((warning) => list.appendChild(el('li', '', warning)));
      const localRows = array(workflow.local_reflections).length;
      const localNodes = array(workflow.nodes).filter((node) => node.kind === 'local_candidate').length;
      if (localRows > localNodes) {
        list.appendChild(el('li', '', `G5 체계도는 금액순 상위 ${localNodes}개 후보만 표시하며, 전체 ${localRows}개 행은 예산·지역 흐름 탭에 보존합니다.`));
      }
      list.appendChild(el('li', '', 'G0–G6는 비교를 위한 표시 분류(presentation taxonomy)이며 원문이 선언한 단계가 아닙니다.'));
      banner.appendChild(list);
    }

    function renderSearchResults() {
      const query = normalized(byId('business-search').value.trim());
      const ministry = byId('ministry-filter').value;
      const matches = SEARCH_INDEX.filter((row) =>
        (!ministry || row.ministry === ministry) && (!query || row.haystack.includes(query))
      ).slice(0, 40);
      const results = byId('search-results');
      results.replaceChildren();
      if (!matches.length) {
        results.appendChild(el('div', 'result-empty', '조건에 맞는 세부사업이 없습니다.'));
      } else {
        matches.forEach((row) => {
          const core = object(row.workflow.core);
          const button = el('button', 'result-button');
          button.type = 'button';
          button.setAttribute('role', 'option');
          const title = el('strong', '', row.workflow.title);
          const amount = el('span', '', compactWon(core.congress_amt));
          const path = el('span', '', [row.ministry, core.program_name, core.unit_business_name].filter(Boolean).join(' · '));
          const level = el('span', '', coverageInfo(row.workflow).label);
          button.append(title, amount, path, level);
          button.addEventListener('click', () => {
            selectBusiness(row.workflow);
            byId('business-search').value = row.workflow.title;
            results.hidden = true;
          });
          results.appendChild(button);
        });
      }
      results.hidden = false;
      return matches;
    }

    function scheduleSearch() {
      window.clearTimeout(state.searchTimer);
      state.searchTimer = window.setTimeout(renderSearchResults, 150);
    }

    function renderEdgeLegend(workflow) {
      const present = [...new Set(array(workflow.edges).map((edge) => edge.type))];
      const legend = byId('edge-legend');
      legend.replaceChildren(el('strong', '', '관계선'));
      state.hiddenEdgeTypes.clear();
      present.forEach((type) => {
        const info = EDGE_INFO[type] || { label: text(type), className: '' };
        const label = el('label', 'edge-toggle');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = true;
        checkbox.value = type;
        const swatch = el('span', `line-swatch ${info.className}`);
        label.append(checkbox, swatch, document.createTextNode(info.label));
        checkbox.addEventListener('change', () => {
          if (checkbox.checked) state.hiddenEdgeTypes.delete(type);
          else state.hiddenEdgeTypes.add(type);
          drawEdges();
          renderRelationList();
        });
        legend.appendChild(label);
      });
      legend.append(badge('api'), badge('documented'), badge('derived'), badge('candidate'));
    }

    function renderNodeCard(node) {
      const button = el('button', `node-card kind-${text(node.kind, 'unknown')}`);
      button.type = 'button';
      button.dataset.nodeId = node.id;
      button.setAttribute('aria-pressed', 'false');
      button.setAttribute('aria-label', `${text(node.display_id, node.id)} ${text(node.label)}. 근거 상세 보기`);
      const top = el('div', 'node-top');
      top.append(el('span', 'node-id', text(node.display_id, node.id)), badge(node.assertion));
      button.append(top, el('span', 'node-label', text(node.label, '이름 없는 노드')));
      const meta = el('span', 'node-meta');
      meta.appendChild(el('span', 'badge', text(node.kind, 'node')));
      if (node.amount_won != null) meta.appendChild(el('span', 'badge', compactWon(node.amount_won)));
      button.appendChild(meta);
      if (node.amount_won != null) button.appendChild(el('span', 'node-amount', won(node.amount_won)));
      button.addEventListener('click', () => selectNode(node.id));
      return button;
    }

    function renderWorkflow(workflow) {
      const empty = byId('workflow-empty');
      const scroll = byId('matrix-scroll');
      const matrix = byId('matrix');
      matrix.replaceChildren();
      empty.replaceChildren();
      empty.hidden = true;
      scroll.hidden = false;
      byId('node-detail').replaceChildren(
        el('h2', '', '노드 근거'),
        el('p', 'muted', '체계도의 노드를 선택하면 내용, 선행·후행 관계, PDF 쪽·청크와 API 필드를 확인할 수 있습니다.'),
      );

      const coverage = object(workflow.coverage);
      if (coverage.level === 'api_only') {
        scroll.hidden = true;
        empty.hidden = false;
        empty.className = 'empty-state';
        empty.append(
          el('strong', '', '확인된 업무 절차가 없습니다.'),
          el('span', '', '열린재정 예산 정본은 확보했지만 설명자료 PDF의 확정 매칭이 없어 절차·행위·관계를 생성하지 않았습니다. 예산·지역 흐름 탭에서 확정액과 목·세목을 확인하세요.'),
        );
        renderEdgeLegend(workflow);
        renderRelationList();
        return;
      }

      const nodes = array(workflow.nodes);
      const nodePhaseIds = new Set(nodes.map((node) => node.phase));
      const phases = array(workflow.phases)
        .filter((phase) => nodePhaseIds.has(phase.id))
        .sort((a, b) => number(a.order) - number(b.order));
      const actors = array(workflow.actors);
      if (!nodes.length || !phases.length || !actors.length) {
        scroll.hidden = true;
        empty.hidden = false;
        empty.className = 'empty-state';
        empty.append(el('strong', '', '표시할 구조화 노드가 없습니다.'), el('span', '', '원자료의 공백을 임의 절차로 채우지 않았습니다.'));
        renderEdgeLegend(workflow);
        renderRelationList();
        return;
      }

      const svg = svgEl('svg', { class: 'edge-layer', 'aria-hidden': 'true' });
      svg.dataset.role = 'edges';
      matrix.appendChild(svg);
      matrix.style.gridTemplateColumns = `var(--stage-width) repeat(${actors.length}, minmax(var(--lane-width), 1fr))`;
      matrix.style.gridTemplateRows = `86px repeat(${phases.length}, minmax(150px, auto))`;
      matrix.style.setProperty('--print-lanes', String(actors.length));

      const corner = el('div', 'matrix-corner', '단계 ↓\n행위자 →');
      corner.style.gridColumn = '1';
      corner.style.gridRow = '1';
      matrix.appendChild(corner);

      actors.forEach((actor, actorIndex) => {
        const header = el('div', 'actor-head');
        header.style.gridColumn = String(actorIndex + 2);
        header.style.gridRow = '1';
        header.append(el('b', '', text(actor.name, '행위자 미상')), el('span', '', text(actor.role, '역할 미상')));
        const assertion = ASSERTION_INFO[actor.assertion];
        if (assertion) header.appendChild(badge(actor.assertion));
        matrix.appendChild(header);
      });

      phases.forEach((phase, phaseIndex) => {
        const row = phaseIndex + 2;
        const header = el('div', 'stage-head');
        header.style.gridColumn = '1';
        header.style.gridRow = String(row);
        header.append(el('b', '', text(phase.id)), el('span', '', text(phase.label)));
        matrix.appendChild(header);

        actors.forEach((actor, actorIndex) => {
          const cell = el('div', 'matrix-cell');
          cell.style.gridColumn = String(actorIndex + 2);
          cell.style.gridRow = String(row);
          cell.dataset.phaseId = phase.id;
          cell.dataset.actorId = actor.id;
          cell.dataset.actorLabel = `${text(actor.name)} · ${text(actor.role)}`;
          nodes
            .filter((node) => node.phase === phase.id && node.actor === actor.id)
            .forEach((node) => cell.appendChild(renderNodeCard(node)));
          matrix.appendChild(cell);
        });
      });

      renderEdgeLegend(workflow);
      renderRelationList();
      if (state.resizeObserver) state.resizeObserver.disconnect();
      if ('ResizeObserver' in window) {
        state.resizeObserver = new ResizeObserver(() => window.requestAnimationFrame(drawEdges));
        state.resizeObserver.observe(matrix);
      }
      window.requestAnimationFrame(() => window.requestAnimationFrame(drawEdges));
    }

    function routePoints(sourceRect, targetRect, matrixRect) {
      const s = {
        left: sourceRect.left - matrixRect.left,
        right: sourceRect.right - matrixRect.left,
        top: sourceRect.top - matrixRect.top,
        bottom: sourceRect.bottom - matrixRect.top,
        cx: (sourceRect.left + sourceRect.right) / 2 - matrixRect.left,
        cy: (sourceRect.top + sourceRect.bottom) / 2 - matrixRect.top,
      };
      const t = {
        left: targetRect.left - matrixRect.left,
        right: targetRect.right - matrixRect.left,
        top: targetRect.top - matrixRect.top,
        bottom: targetRect.bottom - matrixRect.top,
        cx: (targetRect.left + targetRect.right) / 2 - matrixRect.left,
        cy: (targetRect.top + targetRect.bottom) / 2 - matrixRect.top,
      };
      if (Math.abs(s.cy - t.cy) < 44 && Math.abs(s.cx - t.cx) > 20) {
        const forward = t.cx >= s.cx;
        const sx = forward ? s.right : s.left;
        const tx = forward ? t.left : t.right;
        const midX = (sx + tx) / 2;
        return { d: `M ${sx} ${s.cy} L ${midX} ${s.cy} L ${midX} ${t.cy} L ${tx} ${t.cy}`, x: midX, y: (s.cy + t.cy) / 2 };
      }
      const forward = t.cy >= s.cy;
      const sy = forward ? s.bottom : s.top;
      const ty = forward ? t.top : t.bottom;
      const midY = forward ? (sy + ty) / 2 : Math.min(s.top, t.top) - 14;
      return { d: `M ${s.cx} ${sy} L ${s.cx} ${midY} L ${t.cx} ${midY} L ${t.cx} ${ty}`, x: (s.cx + t.cx) / 2, y: midY };
    }

    function relatedPath(nodeId) {
      const edges = array(state.workflow && state.workflow.edges);
      const forward = new Map();
      const backward = new Map();
      edges.forEach((edge) => {
        if (!forward.has(edge.from)) forward.set(edge.from, []);
        if (!backward.has(edge.to)) backward.set(edge.to, []);
        forward.get(edge.from).push(edge);
        backward.get(edge.to).push(edge);
      });
      const upstream = new Set();
      const downstream = new Set();
      const activeEdges = new Set();
      const walk = (start, adjacency, nodes) => {
        const queue = [start];
        const visited = new Set([start]);
        while (queue.length) {
          const current = queue.shift();
          array(adjacency.get(current)).forEach((edge) => {
            activeEdges.add(edge.id);
            const next = adjacency === forward ? edge.to : edge.from;
            nodes.add(next);
            if (!visited.has(next)) {
              visited.add(next);
              queue.push(next);
            }
          });
        }
      };
      walk(nodeId, forward, downstream);
      walk(nodeId, backward, upstream);
      return { upstream, downstream, activeEdges };
    }

    function drawEdges() {
      const workflow = state.workflow;
      const matrix = byId('matrix');
      const svg = matrix.querySelector('svg[data-role="edges"]');
      if (!workflow || !svg || byId('matrix-scroll').hidden) return;
      svg.replaceChildren();
      const width = matrix.scrollWidth;
      const height = matrix.scrollHeight;
      svg.setAttribute('width', String(width));
      svg.setAttribute('height', String(height));
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

      const defs = svgEl('defs');
      const marker = svgEl('marker', {
        id: 'edge-arrow', markerWidth: 8, markerHeight: 8, refX: 7, refY: 4,
        orient: 'auto', markerUnits: 'strokeWidth', viewBox: '0 0 8 8',
      });
      marker.appendChild(svgEl('path', { d: 'M 0 0 L 8 4 L 0 8 z', fill: '#52635b' }));
      defs.appendChild(marker);
      svg.appendChild(defs);

      const selected = state.selectedNodeId ? relatedPath(state.selectedNodeId) : null;
      const matrixRect = matrix.getBoundingClientRect();
      array(workflow.edges).forEach((edge) => {
        if (state.hiddenEdgeTypes.has(edge.type)) return;
        const from = matrix.querySelector(`[data-node-id="${CSS.escape(edge.from)}"]`);
        const to = matrix.querySelector(`[data-node-id="${CSS.escape(edge.to)}"]`);
        if (!from || !to) return;
        const route = routePoints(from.getBoundingClientRect(), to.getBoundingClientRect(), matrixRect);
        const typeInfo = EDGE_INFO[edge.type] || { className: '' };
        const isActive = selected && selected.activeEdges.has(edge.id);
        const isDim = selected && !isActive;
        const path = svgEl('path', {
          d: route.d,
          class: `edge-path type-${typeInfo.className} assertion-${text(edge.assertion, '')}${isActive ? ' is-active' : ''}${isDim ? ' is-dim' : ''}`,
          'marker-end': 'url(#edge-arrow)',
          'data-edge-id': edge.id,
        });
        svg.appendChild(path);

        if (edge.label) {
          const labelText = text(edge.label);
          const labelWidth = Math.min(160, Math.max(42, labelText.length * 5.6 + 12));
          const group = svgEl('g', { class: `edge-label${isDim ? ' is-dim' : ''}` });
          group.appendChild(svgEl('rect', { x: route.x - labelWidth / 2, y: route.y - 9, width: labelWidth, height: 18 }));
          const label = svgEl('text', { x: route.x, y: route.y });
          label.textContent = labelText.length > 24 ? labelText.slice(0, 23) + '…' : labelText;
          group.appendChild(label);
          svg.appendChild(group);
        }
      });
    }

    function selectNode(nodeId) {
      state.selectedNodeId = nodeId;
      const path = relatedPath(nodeId);
      byId('matrix').querySelectorAll('.node-card').forEach((button) => {
        const id = button.dataset.nodeId;
        const selected = id === nodeId;
        const related = path.upstream.has(id) || path.downstream.has(id);
        button.classList.toggle('is-selected', selected);
        button.classList.toggle('is-path', related);
        button.classList.toggle('is-dim', !selected && !related);
        button.setAttribute('aria-pressed', selected ? 'true' : 'false');
      });
      drawEdges();
      renderNodeDetail(nodeId, path);
    }

    function renderNodeDetail(nodeId, path) {
      const workflow = state.workflow;
      const node = array(workflow.nodes).find((item) => item.id === nodeId);
      if (!node) return;
      const actor = array(workflow.actors).find((item) => item.id === node.actor);
      const phase = array(workflow.phases).find((item) => item.id === node.phase);
      const panel = byId('node-detail');
      panel.replaceChildren();
      const top = el('div', 'node-top');
      top.append(el('span', 'node-id', text(node.display_id, node.id)), badge(node.assertion));
      panel.append(top, el('h2', '', text(node.label)));
      addKeyValues(panel, [
        ['단계', phase ? `${phase.id} ${phase.label}` : node.phase],
        ['행위자', actor ? actor.name : null],
        ['역할', actor ? actor.role : null],
        ['노드 유형', node.kind],
        ['금액', node.amount_won == null ? null : won(node.amount_won)],
        ['근거 등급', (ASSERTION_INFO[node.assertion] || {}).label],
      ]);
      if (node.detail) panel.appendChild(el('p', 'detail-copy', node.detail));

      const relationSection = el('section', 'detail-section');
      relationSection.appendChild(el('h3', '', '연결 범위'));
      const nodeMap = new Map(array(workflow.nodes).map((item) => [item.id, item]));
      const upstream = [...path.upstream].map((id) => text(object(nodeMap.get(id)).label, id));
      const downstream = [...path.downstream].map((id) => text(object(nodeMap.get(id)).label, id));
      addKeyValues(relationSection, [
        ['모든 선행', upstream.length ? upstream : ['없음']],
        ['모든 후행', downstream.length ? downstream : ['없음']],
      ]);
      panel.appendChild(relationSection);

      const sources = el('section', 'detail-section');
      sources.appendChild(el('h3', '', '원천 근거'));
      if (!array(node.source_refs).length) sources.appendChild(el('p', 'muted', '개별 원천 참조 없음'));
      array(node.source_refs).forEach((ref) => sources.appendChild(el('div', 'source-ref', sourceRefText(ref))));
      panel.appendChild(sources);

      const evidenceIds = new Set(array(node.source_refs).map((ref) => ref.evidence_id).filter(Boolean));
      const evidence = array(workflow.evidence_sections).filter((item) => evidenceIds.has(item.id));
      if (evidence.length) {
        const originals = el('section', 'detail-section');
        originals.appendChild(el('h3', '', '연결된 설명자료 원문'));
        evidence.forEach((item) => {
          const details = el('details', 'evidence-item');
          const summary = el('summary');
          summary.append(el('span', '', item.label), el('span', '', pages(item.page_start, item.page_end)));
          const body = el('div', 'evidence-body');
          body.appendChild(el('pre', 'evidence-text', item.text));
          details.append(summary, body);
          originals.appendChild(details);
        });
        panel.appendChild(originals);
      }
    }

    function renderRelationList() {
      const list = byId('relation-list');
      list.replaceChildren();
      const workflow = state.workflow;
      if (!workflow) return;
      const nodeMap = new Map(array(workflow.nodes).map((node) => [node.id, node]));
      const visibleEdges = array(workflow.edges).filter((edge) => !state.hiddenEdgeTypes.has(edge.type));
      if (!visibleEdges.length) {
        list.appendChild(el('li', 'muted', '표시할 관계가 없습니다. 원문에 없는 순서를 추가하지 않았습니다.'));
        return;
      }
      visibleEdges.forEach((edge) => {
        const from = object(nodeMap.get(edge.from));
        const to = object(nodeMap.get(edge.to));
        const item = document.createElement('li');
        const fromButton = el('button', '', `${text(from.display_id, from.id)} ${text(from.label, edge.from)}`);
        fromButton.type = 'button';
        fromButton.addEventListener('click', () => selectNode(edge.from));
        const toButton = el('button', '', `${text(to.display_id, to.id)} ${text(to.label, edge.to)}`);
        toButton.type = 'button';
        toButton.addEventListener('click', () => selectNode(edge.to));
        const edgeInfo = EDGE_INFO[edge.type] || { label: text(edge.type) };
        const assertion = (ASSERTION_INFO[edge.assertion] || {}).label || text(edge.assertion);
        item.append(
          fromButton,
          document.createTextNode(` → ${edgeInfo.label} / ${text(edge.label)} / ${assertion} → `),
          toButton,
        );
        list.appendChild(item);
      });
    }

    function makeTable(headers, rows, numericColumns = new Set()) {
      const wrap = el('div', 'table-wrap');
      const table = document.createElement('table');
      const thead = document.createElement('thead');
      const headerRow = document.createElement('tr');
      headers.forEach((header) => headerRow.appendChild(el('th', '', header)));
      thead.appendChild(headerRow);
      const tbody = document.createElement('tbody');
      rows.forEach((row) => {
        const tr = document.createElement('tr');
        row.forEach((value, index) => tr.appendChild(el('td', numericColumns.has(index) ? 'num' : '', value)));
        tbody.appendChild(tr);
      });
      table.append(thead, tbody);
      wrap.appendChild(table);
      return wrap;
    }

    function renderBudget(workflow) {
      const core = object(workflow.core);
      const channels = array(workflow.execution_channels);
      const breakdown = array(workflow.budget_breakdown);
      const locals = array(workflow.local_reflections);
      const content = byId('budget-content');
      content.replaceChildren();

      const grid = el('div', 'budget-grid');
      const flow = el('section', 'panel-card budget-card');
      const flowHead = el('div', 'section-head');
      flowHead.append(el('h2', '', '중앙예산 집행채널'), el('p', '', '금액은 열린재정 국회확정액·목·세목 합계입니다.'));
      flow.appendChild(flowHead);
      const amountHero = el('div', 'amount-hero');
      amountHero.append(el('span', '', `${text(core.office_name)} · ${text(core.detail_business_name, workflow.title)}`), el('strong', '', won(core.congress_amt)));
      flow.append(amountHero, el('div', 'flow-arrow', '↓ ExpenditureBudgetAdd2 목·세목 규칙 분류'));
      const stack = el('div', 'channel-stack');
      channels.forEach((channel) => {
        const card = el('article', 'channel-card');
        const title = el('div', 'channel-title');
        title.append(el('b', '', `${text(channel.label)} · ${text(channel.code)}`), el('b', '', compactWon(channel.amount_won)));
        const track = el('div', 'share-track');
        const bar = el('div', 'share-bar');
        bar.style.width = `${Math.max(0, Math.min(100, number(channel.share) * 100))}%`;
        track.appendChild(bar);
        card.append(title, track, el('small', '', `비중 ${percent(channel.share)} · 원자료 ${number(channel.line_count).toLocaleString('ko-KR')}행`));
        if (channel.code === 'direct') {
          card.appendChild(el('div', 'warning-box', 'direct는 다른 채널 규칙에 걸리지 않은 비목의 잔여(catch-all) 분류입니다. 실제 직접수행을 확정하는 증거가 아닙니다.'));
        }
        stack.appendChild(card);
      });
      if (!channels.length) stack.appendChild(el('div', 'empty-state', '표시할 집행채널이 없습니다.'));
      flow.appendChild(stack);

      if (locals.length) {
        const bridge = el('div', 'candidate-bridge');
        bridge.append(
          el('strong', '', `⋯⋯ LOFIN keyword_candidate ${locals.length.toLocaleString('ko-KR')}행 ⋯→`),
          document.createTextNode(' 중앙사업 검색어에서 발견된 지방사업 후보입니다. 확정 교부 관계가 아닙니다.'),
        );
        flow.appendChild(bridge);
      }
      grid.appendChild(flow);

      const breakdownCard = el('section', 'panel-card budget-card');
      const breakHead = el('div', 'section-head');
      breakHead.append(el('h2', '', '목·세목 구성'), el('p', '', '동일 수준 항목끼리만 합산 가능한 API 정본입니다.'));
      breakdownCard.appendChild(breakHead);
      breakdownCard.appendChild(makeTable(
        ['목', '세목', '금액', '비중', '원자료 행', '금액 필드'],
        breakdown.map((row) => [
          text(row.mok_name), text(row.semok_name), won(row.amount_won), percent(row.share),
          number(row.line_count).toLocaleString('ko-KR'), text(row.amount_field),
        ]),
        new Set([2, 3, 4]),
      ));
      grid.appendChild(breakdownCard);
      content.appendChild(grid);

      const localSection = el('section', 'panel-card subsection');
      const localHead = el('div', 'section-head');
      localHead.append(
        el('h2', '', `LOFIN 지역 반영 후보 ${locals.length.toLocaleString('ko-KR')}행`),
        el('p', '', 'QWGJK 기준일 스냅샷 · 관계 상태 keyword_candidate'),
      );
      localSection.appendChild(localHead);
      if (!locals.length) {
        localSection.appendChild(el('div', 'empty-state', '연결된 LOFIN 키워드 후보가 없습니다. 이는 지역 미집행을 의미하지 않습니다.'));
      } else {
        const warning = el('div', 'warning-box',
          text(object(workflow.local_summary).sum_warning,
            '광역·기초 행은 같은 재원을 중복 표현할 수 있고 공유 키워드 중복도 있으므로 중앙예산과 합계 대사하지 않습니다.')
        );
        localSection.appendChild(warning);
        localSection.appendChild(makeTable(
          ['지자체·단계', '지방 세부사업', '국비', '시도비', '시군구비', '예산현액', '편성액', '지출액', '기준일', '후보 상태'],
          locals.map((row) => [
            `${text(row.local_gov_name)} · ${text(row.local_level)}`,
            `${text(row.detail_business_name)}${row.detail_business_code ? `\n${row.detail_business_code}` : ''}`,
            won(row.national_amt), won(row.sido_amt), won(row.sigungu_amt), won(row.budget_cash_amt),
            won(row.compile_amt), won(row.spend_amt), formatDate(row.exe_ymd),
            `${text(row.match_status)}${row.shared_keyword_duplicate ? ' · 공유키워드 중복' : ''}${row.additive === false ? ' · 합산불가' : ''}`,
          ]),
          new Set([2, 3, 4, 5, 6, 7]),
        ));
      }
      content.appendChild(localSection);
    }

    function renderEvidence(workflow) {
      const content = byId('evidence-content');
      content.replaceChildren();
      const coverage = object(workflow.coverage);
      const info = coverageInfo(workflow);
      const locals = array(workflow.local_reflections);
      const sections = array(workflow.evidence_sections);
      const pdfCards = array(workflow.pdf_cards);

      const summary = el('section', 'panel-card subsection');
      const summaryHead = el('div', 'section-head');
      summaryHead.append(el('h2', '', '소스별 커버리지'), el('p', '', '출처와 주장 강도를 분리해 검증합니다.'));
      summary.appendChild(summaryHead);
      const cards = el('div', 'evidence-grid');
      [
        ['열린재정 API', '정본 확보', `ExpenditureBudgetAdd2 · ${text(object(workflow.core).year)} · Y_YY_DFN_KCUR_AMT`],
        ['설명자료 PDF', info.label, `${pdfCards.length.toLocaleString('ko-KR')}개 카드 · ${sections.length.toLocaleString('ko-KR')}개 근거 섹션`],
        ['LOFIN QWGJK', locals.length ? 'keyword_candidate' : '연결 후보 없음', `${locals.length.toLocaleString('ko-KR')}개 후보 행 · 합계 대사 금지`],
      ].forEach(([label, value, description]) => {
        const card = el('article', 'coverage-card');
        card.append(el('span', '', label), el('strong', '', value), el('p', '', description));
        cards.appendChild(card);
      });
      summary.appendChild(cards);
      content.appendChild(summary);

      const boundary = el('section', 'panel-card subsection');
      const boundaryHead = el('div', 'section-head');
      boundaryHead.append(el('h2', '', '해석 경계'), el('p', '', '원자료보다 강한 주장을 만들지 않는 규칙입니다.'));
      boundary.appendChild(boundaryHead);
      const rules = el('ul', 'interpretation-list');
      rules.appendChild(el('li', '', 'G0–G6는 사업 간 비교를 위한 표시 분류이며, 원문이 선언한 단계 이름이 아닙니다.'));
      rules.appendChild(el('li', '', 'documented는 설명자료 문구·표에서 확인된 사실, API는 열린재정 정본, derived는 표시용 파생, candidate는 미확정 후보입니다.'));
      if (array(workflow.execution_channels).some((channel) => channel.code === 'direct')) {
        rules.appendChild(el('li', '', 'direct는 목·세목 규칙의 잔여(catch-all) 분류로 실제 직접수행의 증거가 아닙니다.'));
      }
      if (locals.length) {
        rules.appendChild(el('li', '', 'LOFIN은 키워드 후보 연결이며 광역·기초 중복과 공유 검색어 중복이 있어 중앙예산과 합계 대사하지 않습니다.'));
      }
      array(coverage.warnings).forEach((warning) => rules.appendChild(el('li', '', warning)));
      boundary.appendChild(rules);
      content.appendChild(boundary);

      const coreSection = el('section', 'panel-card subsection');
      const coreHead = el('div', 'section-head');
      coreHead.append(el('h2', '', '열린재정 API 필드'), el('p', '', '예산 분류와 금액의 source of truth'));
      coreSection.appendChild(coreHead);
      const core = object(workflow.core);
      coreSection.appendChild(makeTable(
        ['의미', '필드', '값'],
        [
          ['기준연도', 'year', text(core.year)], ['소관', 'office_name', text(core.office_name)],
          ['회계', 'account_name', text(core.account_name)], ['분야', 'field_name', text(core.field_name)],
          ['부문', 'section_name', text(core.section_name)], ['프로그램', 'program_name', text(core.program_name)],
          ['단위사업', 'unit_business_name', text(core.unit_business_name)],
          ['세부사업', 'detail_business_name', text(core.detail_business_name)],
          ['국회확정액', 'Y_YY_DFN_KCUR_AMT', won(core.congress_amt)],
          ['원자료 행', 'line_count', number(core.line_count).toLocaleString('ko-KR')],
        ],
      ));
      content.appendChild(coreSection);

      const pdfSection = el('section', 'panel-card subsection');
      const pdfHead = el('div', 'section-head');
      pdfHead.append(el('h2', '', `PDF 매칭 카드 ${pdfCards.length.toLocaleString('ko-KR')}개`), el('p', '', '파일·페이지·청크·매칭 방법'));
      pdfSection.appendChild(pdfHead);
      if (!pdfCards.length) {
        pdfSection.appendChild(el('div', 'empty-state', '확정 매칭된 설명자료 PDF 카드가 없습니다.'));
      } else {
        const grid = el('div', 'pdf-card-grid');
        pdfCards.forEach((card) => {
          const article = el('article', 'pdf-card');
          article.appendChild(el('strong', '', text(card.clean_title, card.raw_title)));
          addKeyValues(article, [
            ['사업 코드', card.code_hint], ['시행 경로', array(card.exec_paths)],
            ['PDF', card.source_pdf], ['페이지', pages(card.page_start, card.page_end)],
            ['청크', [card.source_chunk_start, card.source_chunk_end].filter(Boolean).join('–')],
            ['매칭', [card.confidence, card.method, card.score == null ? null : `${card.score}점`].filter(Boolean)],
          ]);
          grid.appendChild(article);
        });
        pdfSection.appendChild(grid);
      }
      content.appendChild(pdfSection);

      const evidenceSection = el('section', 'panel-card subsection');
      const evidenceHead = el('div', 'section-head');
      evidenceHead.append(el('h2', '', `설명자료 근거 섹션 ${sections.length.toLocaleString('ko-KR')}개`), el('p', '', '노드가 참조하는 실제 문서 구간'));
      evidenceSection.appendChild(evidenceHead);
      const list = el('div', 'evidence-list');
      if (!sections.length) list.appendChild(el('div', 'empty-state', '표시할 설명자료 근거 섹션이 없습니다.'));
      sections.forEach((item) => {
        const details = el('details', 'evidence-item');
        const summaryNode = el('summary');
        summaryNode.append(
          el('span', '', `${text(item.label)} · ${text(item.section)}`),
          el('span', '', `${text(item.source_pdf)} · ${pages(item.page_start, item.page_end)} · ${text(item.chunk_start)}–${text(item.chunk_end)}`),
        );
        const body = el('div', 'evidence-body');
        const match = object(item.match);
        addKeyValues(body, [
          ['근거 ID', item.id], ['매칭', [match.confidence, match.method, match.score == null ? null : `${match.score}점`].filter(Boolean)],
        ]);
        body.appendChild(el('pre', 'evidence-text', item.text));
        details.append(summaryNode, body);
        list.appendChild(details);
      });
      evidenceSection.appendChild(list);
      content.appendChild(evidenceSection);
    }

    function selectBusiness(workflow) {
      if (!workflow) return;
      state.workflow = workflow;
      state.selectedNodeId = null;
      renderHeader(workflow);
      renderWorkflow(workflow);
      renderBudget(workflow);
      renderEvidence(workflow);
      const hash = `#business=${encodeURIComponent(workflow.id)}&tab=${encodeURIComponent(state.activeTab)}`;
      if (window.location.hash !== hash) history.replaceState(null, '', hash);
      if (state.activeTab === 'workflow') window.requestAnimationFrame(drawEdges);
    }

    function setTab(tabName, focus = false) {
      const allowed = new Set(['workflow', 'budget', 'evidence']);
      if (!allowed.has(tabName)) tabName = 'workflow';
      state.activeTab = tabName;
      document.querySelectorAll('[role="tab"][data-tab]').forEach((button) => {
        const active = button.dataset.tab === tabName;
        button.setAttribute('aria-selected', active ? 'true' : 'false');
        button.tabIndex = active ? 0 : -1;
        if (active && focus) button.focus();
      });
      document.querySelectorAll('.tab-panel').forEach((panel) => {
        panel.hidden = panel.id !== `tab-${tabName}`;
      });
      if (state.workflow) {
        const hash = `#business=${encodeURIComponent(state.workflow.id)}&tab=${encodeURIComponent(tabName)}`;
        history.replaceState(null, '', hash);
      }
      if (tabName === 'workflow') window.requestAnimationFrame(() => window.requestAnimationFrame(drawEdges));
    }

    function parseHash() {
      const raw = window.location.hash.replace(/^#/, '');
      const params = new URLSearchParams(raw);
      return { business: params.get('business'), tab: params.get('tab') };
    }

    function initialWorkflow() {
      const hash = parseHash();
      const fromHash = WORKFLOWS.find((workflow) => workflow.id === hash.business);
      const fromMeta = WORKFLOWS.find((workflow) => workflow.id === META.default_business_id);
      const preferred = WORKFLOWS.find((workflow) => normalized(workflow.title).includes(normalized('한국지방행정연구원정책개발연구등지원')));
      return { workflow: fromHash || fromMeta || preferred || WORKFLOWS[0], tab: hash.tab || 'workflow' };
    }

    function wireEvents() {
      byId('business-search').addEventListener('input', scheduleSearch);
      byId('business-search').addEventListener('focus', renderSearchResults);
      byId('business-search').addEventListener('keydown', (event) => {
        if (event.key === 'Escape') byId('search-results').hidden = true;
        if (event.key === 'Enter') {
          const matches = renderSearchResults();
          if (matches.length) {
            event.preventDefault();
            selectBusiness(matches[0].workflow);
            byId('business-search').value = matches[0].workflow.title;
            byId('search-results').hidden = true;
          }
        }
      });
      byId('ministry-filter').addEventListener('change', () => {
        if (state.workflow && byId('business-search').value === state.workflow.title) {
          byId('business-search').value = '';
        }
        const matches = renderSearchResults();
        if (matches.length && (!state.workflow || (byId('ministry-filter').value && object(state.workflow.core).office_name !== byId('ministry-filter').value))) {
          selectBusiness(matches[0].workflow);
          byId('business-search').value = matches[0].workflow.title;
          byId('search-results').hidden = true;
        }
      });
      document.addEventListener('click', (event) => {
        if (!event.target.closest('.field.search')) byId('search-results').hidden = true;
      });
      const tabs = [...document.querySelectorAll('[role="tab"][data-tab]')];
      tabs.forEach((button, index) => {
        button.addEventListener('click', () => setTab(button.dataset.tab));
        button.addEventListener('keydown', (event) => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          let nextIndex = index;
          if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
          if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
          if (event.key === 'Home') nextIndex = 0;
          if (event.key === 'End') nextIndex = tabs.length - 1;
          setTab(tabs[nextIndex].dataset.tab, true);
        });
      });
      window.addEventListener('resize', () => window.requestAnimationFrame(drawEdges), { passive: true });
      window.addEventListener('beforeprint', drawEdges);
    }

    setupMinistries();
    wireEvents();
    const initial = initialWorkflow();
    state.activeTab = ['workflow', 'budget', 'evidence'].includes(initial.tab) ? initial.tab : 'workflow';
    selectBusiness(initial.workflow);
    byId('business-search').value = initial.workflow.title;
    byId('ministry-filter').value = text(object(initial.workflow.core).office_name, '');
    setTab(state.activeTab);
  </script>
</body>
</html>
"""


def build_html(payload: dict, year: int) -> str:
    return (
        HTML_TEMPLATE.replace("__PAYLOAD__", safe_json_for_html(payload))
        .replace("__YEAR__", str(year))
        .replace("__SOURCE__", html.escape(SOURCE.name))
    )


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    payload = load_payload(SOURCE)
    workflows, year = validate_payload(payload)
    document = build_html(payload, year)
    year_out = OUT.with_name(f"detailed_business_workflows_{year}.html")
    atomic_write(OUT, document)
    atomic_write(year_out, document)
    print(f"wrote {OUT}")
    print(f"wrote {year_out}")
    print(
        "workflow_html "
        f"businesses={len(workflows)} "
        f"bytes={len(document.encode('utf-8'))} "
        f"default={payload.get('meta', {}).get('default_business_id', workflows[0].get('id'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
