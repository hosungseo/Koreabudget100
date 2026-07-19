#!/usr/bin/env python3
"""Fetch the legacy TotalExpenditure1 service for comparison only.

This script intentionally writes only ``legacy_totalexpenditure1_*`` artifacts.
Canonical and ``*_latest`` aliases belong to fetch_expenditure_budget_add2.py.
"""

from __future__ import annotations
import argparse, json, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
RAW = DATA / 'raw' / 'openfiscal'
NORM = DATA / 'normalized'
UA = {'User-Agent': 'Koreabudget100/0.1'}
SERVICE = 'https://openapi.openfiscaldata.go.kr/TotalExpenditure1'
PILOTS = ['행정안전부', '국토교통부', '산업통상부', '산업통상자원부']

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Fetch legacy TotalExpenditure1 comparison data (never canonical/latest outputs).'
    )
    parser.add_argument('--year', type=int, help='Fiscal year; otherwise detect the latest available year')
    return parser.parse_args(argv)

def load_key():
    for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines():
        if line.startswith('OPENFISCAL_API_KEY='):
            return line.split('=', 1)[1].strip()
    raise SystemExit('OPENFISCAL_API_KEY missing')

def parse_json_payload(text):
    data = json.loads(text)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            pass
    return data

def fetch_page(key, params):
    q = {
        'Key': key,
        'Type': 'json',
        'pIndex': str(params.get('pIndex', 1)),
        'pSize': str(params.get('pSize', 1000)),
        'FSCL_YY': str(params['FSCL_YY']),
    }
    for k in ('OFFC_NM','FSCL_NM','ACCT_NM','FLD_NM','SECT_NM','PGM_NM','ACTV_NM','SACTV_NM','ANEXP_INQ_STND_CD','BDG_FND_DIV_CD'):
        if params.get(k) not in (None, ''):
            q[k] = params[k]
    url = SERVICE + '?' + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return parse_json_payload(resp.read().decode('utf-8', errors='replace'))
    except urllib.error.HTTPError as err:
        body = err.read().decode('utf-8', errors='replace')
        raise RuntimeError('HTTP %s: %s' % (err.code, body[:300])) from err

def extract_rows(payload):
    meta = {'payload_type': type(payload).__name__}
    rows = []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)], meta
    if not isinstance(payload, dict):
        meta['raw_preview'] = str(payload)[:300]
        return [], meta
    if isinstance(payload.get('RESULT'), dict) and len(payload) == 1:
        meta['RESULT'] = payload['RESULT']
        return [], meta
    for key, val in payload.items():
        if key == 'RESULT' or not isinstance(val, list):
            continue
        meta['list_key'] = key
        for item in val:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get('head'), list):
                for h in item['head']:
                    if isinstance(h, dict):
                        if 'list_total_count' in h:
                            meta['list_total_count'] = h.get('list_total_count')
                        if isinstance(h.get('RESULT'), dict):
                            meta['RESULT'] = h['RESULT']
            if isinstance(item.get('row'), list):
                rows.extend([r for r in item['row'] if isinstance(r, dict)])
        if rows:
            break
    if not rows:
        for key, val in payload.items():
            if key == 'RESULT':
                continue
            if isinstance(val, list) and val and isinstance(val[0], dict):
                if any(('row' in x or 'head' in x) for x in val if isinstance(x, dict)):
                    continue
                rows = [x for x in val if isinstance(x, dict)]
                meta['list_key'] = key
                break
    return rows, meta

def fetch_all(key, base_params, max_pages=100):
    all_rows = []
    pages_meta = []
    psize = int(base_params.get('pSize', 1000))
    for page in range(1, max_pages + 1):
        params = dict(base_params)
        params['pIndex'] = page
        params['pSize'] = psize
        payload = fetch_page(key, params)
        rows, meta = extract_rows(payload)
        pages_meta.append({'page': page, 'meta': meta, 'n': len(rows)})
        if not rows:
            if page == 1:
                RAW.mkdir(parents=True, exist_ok=True)
                (RAW / ('debug_%s_p1.json' % base_params.get('OFFC_NM', 'x'))).write_text(json.dumps(payload, ensure_ascii=False, indent=2)[:300000], encoding='utf-8')
            break
        all_rows.extend(rows)
        total = None
        if 'list_total_count' in meta:
            try:
                total = int(meta['list_total_count'])
            except Exception:
                total = None
        if total is not None and len(all_rows) >= total:
            break
        if len(rows) < psize:
            break
        time.sleep(0.15)
    return all_rows, pages_meta

def to_num(v):
    if v is None or v == '':
        return None
    try:
        return float(str(v).replace(',', ''))
    except Exception:
        return None

def pick(row, *names):
    lower_map = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name in row and row[name] not in (None, ''):
            return row[name]
        v = lower_map.get(name.lower())
        if v not in (None, ''):
            return v
    return None

def normalize(rows, ministry, year):
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append({
            'year': year,
            'ministry_query': ministry,
            'office_name': pick(r, 'OFFC_NM'),
            'account_name': pick(r, 'FSCL_NM'),
            'acct_name': pick(r, 'ACCT_NM'),
            'field_name': pick(r, 'FLD_NM'),
            'section_name': pick(r, 'SECT_NM'),
            'program_name': pick(r, 'PGM_NM'),
            'unit_business_name': pick(r, 'ACTV_NM'),
            'detail_business_name': pick(r, 'SACTV_NM'),
            'prev_first_amt': to_num(pick(r, 'Y_PREY_FIRST_KCUR_AMT')),
            'prev_final_amt': to_num(pick(r, 'Y_PREY_FNL_KCUR_AMT')),
            'gov_draft_amt': to_num(pick(r, 'Y_YY_MEDI_KCUR_AMT')),
            'congress_amt': to_num(pick(r, 'Y_YY_DFN_MEDI_KCUR_AMT')),
            'raw': r,
        })
    return out

def build_tree(rows):
    root = {'name': 'root', 'children': {}, 'amount': 0.0, 'count': 0}
    def ensure(node, name):
        ch = node['children']
        if name not in ch:
            ch[name] = {'name': name, 'children': {}, 'amount': 0.0, 'count': 0}
        return ch[name]
    for r in rows:
        amt = float(r.get('congress_amt') or 0.0)
        m = ensure(root, r.get('office_name') or r.get('ministry_query') or 'UNKNOWN')
        a = ensure(m, r.get('account_name') or '(회계미상)')
        p = ensure(a, r.get('program_name') or '(프로그램미상)')
        u = ensure(p, r.get('unit_business_name') or '(단위사업미상)')
        d = ensure(u, r.get('detail_business_name') or '(세부사업미상)')
        d['amount'] += amt
        d['count'] += 1
        for n in (u, p, a, m, root):
            n['amount'] += amt
            n['count'] = n.get('count', 0) + 1
    return root

def tree_to_jsonable(node):
    children = [tree_to_jsonable(c) for c in node['children'].values()]
    children.sort(key=lambda x: x.get('amount') or 0, reverse=True)
    out = {'name': node['name'], 'amount': node.get('amount', 0), 'count': node.get('count', 0)}
    if children:
        out['children'] = children
    return out

def detect_year(key):
    for year in range(2026, 2017, -1):
        payload = fetch_page(key, {'FSCL_YY': year, 'pIndex': 1, 'pSize': 1})
        rows, meta = extract_rows(payload)
        code = meta.get('RESULT', {}).get('CODE') if isinstance(meta.get('RESULT'), dict) else None
        if rows or code == 'INFO-000' or meta.get('list_total_count'):
            print('year_detected', year, 'sample_rows', len(rows), 'total', meta.get('list_total_count'), 'code', code)
            return year
        print('year_empty', year, 'code', code or meta)
        time.sleep(0.1)
    raise SystemExit('no year with data found')

def main(argv=None):
    args = parse_args(argv)
    key = load_key()
    RAW.mkdir(parents=True, exist_ok=True)
    NORM.mkdir(parents=True, exist_ok=True)
    year = args.year if args.year is not None else detect_year(key)
    summary = []
    all_norm = []
    for ministry in PILOTS:
        print('== %s %s ==' % (ministry, year))
        base = {'FSCL_YY': year, 'OFFC_NM': ministry, 'pSize': 1000}
        try:
            rows, pages = fetch_all(key, base)
        except Exception as err:
            print(' error', err)
            summary.append({'ministry': ministry, 'error': str(err)})
            continue
        raw_path = RAW / ('TotalExpenditure1_%s_%s.json' % (year, ministry))
        raw_path.write_text(json.dumps({'pages': pages, 'rows': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
        norm = normalize(rows, ministry, year)
        all_norm.extend(norm)
        total = sum((x.get('congress_amt') or 0) for x in norm)
        print(' rows=%s congress_sum=%s' % (len(norm), format(total, ',.0f')))
        summary.append({
            'ministry': ministry,
            'year': year,
            'rows': len(norm),
            'congress_sum': total,
            'sample_names': [x.get('detail_business_name') for x in norm[:5]],
            'pages': [{'page': p['page'], 'n': p['n'], 'total': p['meta'].get('list_total_count')} for p in pages[:3]],
        })
        time.sleep(0.2)
    tree = tree_to_jsonable(build_tree(all_norm))
    (NORM / ('legacy_totalexpenditure1_%s_pilots.json' % year)).write_text(json.dumps(all_norm, ensure_ascii=False, indent=2), encoding='utf-8')
    (NORM / ('legacy_totalexpenditure1_tree_%s_pilots.json' % year)).write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding='utf-8')
    summary_obj = {
        'year': year,
        'service': 'TotalExpenditure1',
        'canonical': False,
        'legacy_comparison_only': True,
        'ministries': summary,
        'total_rows': len(all_norm),
    }
    (DATA / ('fetch_summary_legacy_totalexpenditure1_%s.json' % year)).write_text(json.dumps(summary_obj, ensure_ascii=False, indent=2), encoding='utf-8')
    print('total_rows', len(all_norm))
    print('year', year)

if __name__ == '__main__':
    main()
