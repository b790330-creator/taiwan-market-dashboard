#!/usr/bin/env python3
"""Walk-forward check of simple next-day-direction rules on docs/data/index_history.json.
Writes docs/data/backtest.json (hit rate overall / last 120 / last 60 / last 20 days)."""
from __future__ import annotations
import json, sys
import update as u

def main():
    try: hist = json.loads((u.DATA_DIR / 'index_history.json').read_text(encoding='utf-8'))
    except Exception as e:
        print(f'no history: {e}'); return 0
    dates = sorted(hist); c = [hist[d] for d in dates]; n = len(c)
    if n < 90: print(f'history too short: {n}'); return 0
    def ma(i, k): return sum(c[i-k+1:i+1]) / k
    def ret(i, k): return c[i] / c[i-k] - 1
    def streak(i):
        s = 0; sign = 1 if c[i] > c[i-1] else -1
        while i-s-1 >= 0 and ((c[i-s] > c[i-s-1]) == (sign == 1)) and s < 10: s += 1
        return sign * s
    rules = {
        'always_up': lambda i: True,
        'continue_1d': lambda i: c[i] > c[i-1],
        'reverse_1d': lambda i: c[i] < c[i-1],
        'ret5_pos': lambda i: ret(i,5) > 0,
        'ret5_neg_reversal': lambda i: ret(i,5) < 0,
        'above_ma20': lambda i: c[i] > ma(i,20),
        'above_ma60': lambda i: c[i] > ma(i,60),
        'ma5_above_ma20': lambda i: ma(i,5) > ma(i,20),
        'trend_follow_combo': lambda i: (c[i] > ma(i,20)) and (ret(i,5) > -0.03),
        'trend_follow_ma20_ret1': lambda i: (c[i] > ma(i,20)) or (c[i] < c[i-1]*0.98),
        'oversold_bounce_only_in_uptrend': lambda i: (c[i] > ma(i,60)) == (c[i] < c[i-1]) if False else ((c[i] > ma(i,60)) if c[i] < c[i-1] else (c[i] > ma(i,20))),
        'big_drop_reversal': lambda i: (c[i]/c[i-1]-1 <= -0.02) or (c[i] > ma(i,20)),
    }
    start = 60; out = {'n_days': n - start - 1, 'first': dates[start], 'last': dates[-2], 'rules': {}}
    ups = [c[i+1] > c[i] for i in range(start, n-1)]
    out['base_up_rate'] = round(sum(ups)/len(ups), 3)
    out['base_up_rate_last60'] = round(sum(ups[-60:])/len(ups[-60:]), 3)
    for name, f in rules.items():
        hits = [bool(f(i)) == (c[i+1] > c[i]) for i in range(start, n-1)]
        def rate(xs): return round(sum(xs)/len(xs), 3) if xs else None
        out['rules'][name] = {'all': rate(hits), 'last120': rate(hits[-120:]), 'last60': rate(hits[-60:]), 'last20': rate(hits[-20:])}
    # conditional up-rate buckets
    buckets = {}
    for i in range(start, n-1):
        key = ('above_ma20' if c[i] > ma(i,20) else 'below_ma20') + '|' + ('ret5_pos' if ret(i,5) > 0 else 'ret5_neg') + '|' + ('d1_up' if c[i] > c[i-1] else 'd1_down')
        b = buckets.setdefault(key, [0, 0]); b[0] += 1; b[1] += (c[i+1] > c[i])
    out['buckets'] = {k: {'n': v[0], 'up_rate': round(v[1]/v[0], 3)} for k, v in sorted(buckets.items())}
    (u.DATA_DIR / 'backtest.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(out, ensure_ascii=False)[:1500]); return 0

if __name__ == '__main__':
    sys.exit(main())
