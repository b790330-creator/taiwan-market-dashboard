#!/usr/bin/env python3
"""Maintain docs/data/index_history.json: daily TAIEX close from TWSE FMTQIK (official).
First run backfills ~14 months; later runs only refresh the last 2 months. Best-effort."""
from __future__ import annotations
import json, sys
from datetime import datetime, timedelta
import update as u

PATH = u.DATA_DIR / 'index_history.json'
URL = 'https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={ymd}&response=json'

def month_starts(n):
    d = datetime.now(u.TAIPEI).date().replace(day=1); out = []
    for _ in range(n):
        out.append(d); d = (d - timedelta(days=1)).replace(day=1)
    return out

def parse(payload):
    rows = {}
    for r in payload.get('data', []) or []:
        try:
            y, m, d = str(r[0]).split('/'); date = f'{int(y)+1911:04d}-{int(m):02d}-{int(d):02d}'
            close = float(str(r[4]).replace(',', ''))
            rows[date] = close
        except Exception:
            continue
    return rows

def main():
    try: hist = json.loads(PATH.read_text(encoding='utf-8'))
    except Exception: hist = {}
    months = 2 if len(hist) > 200 else 14
    got = 0
    for d in month_starts(months):
        try:
            rows = parse(u.get_json(URL.format(ymd=d.strftime('%Y%m%d')), attempts=2))
            hist.update(rows); got += len(rows)
        except Exception as e:
            print(f'month {d} failed: {e}')
    if hist:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(json.dumps(dict(sorted(hist.items())), ensure_ascii=False), encoding='utf-8')
    print(f'history: fetched {got} rows, total {len(hist)}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
