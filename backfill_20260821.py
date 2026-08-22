#!/usr/bin/env python3
# One-time historical backfill for 2026-08-21 (TWSE official RWD historical endpoint).
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'docs' / 'data'
DATE = '20260821'
ISO = '2026-08-21'


def get_json(url):
    req = Request(url, headers={'User-Agent': 'taiwan-market-dashboard/1.0'})
    with urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8-sig'))


def num(v):
    s = str(v or '').strip().replace(',', '')
    if s in {'', '--', '-', 'X'}: return None
    try: return float(s)
    except ValueError: return None


def records(payload):
    if isinstance(payload, list): return payload
    fields = payload.get('fields', [])
    rows = payload.get('data', [])
    return [dict(zip(fields, row)) for row in rows if isinstance(row, list)]


def stock_data():
    url = 'https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?' + urlencode({'response':'json','date':DATE})
    payload = get_json(url)
    rows = records(payload)
    out=[]
    for r in rows:
        # RWD fields are Chinese; tolerate English variants too.
        code=str(r.get('證券代號') or r.get('Code') or '').strip()
        name=str(r.get('證券名稱') or r.get('Name') or '').strip()
        close=num(r.get('收盤價') or r.get('ClosingPrice'))
        change=num(r.get('漲跌價') or r.get('Change'))
        if not code or not name or close is None or change is None: continue
        prev=close-change
        pct=(change/prev*100) if prev else 0
        out.append({'code':code,'name':name,'open':num(r.get('開盤價') or r.get('OpeningPrice')),'high':num(r.get('最高價') or r.get('HighestPrice')),'low':num(r.get('最低價') or r.get('LowestPrice')),'close':close,'change':change,'pct':pct,'volume':num(r.get('成交股數') or r.get('TradeVolume')) or 0,'transactions':num(r.get('成交筆數') or r.get('Transaction')) or 0,'value':num(r.get('成交金額') or r.get('TradeValue')) or 0})
    if len(out) < 100: raise RuntimeError(f'Historical stock data incomplete: {len(out)}')
    return out


def index_data():
    url = 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?' + urlencode({'response':'json','date':DATE,'type':'ALL'})
    payload=get_json(url)
    rows=records(payload)
    target=next((r for r in rows if str(r.get('指數') or r.get('IndexName') or '') == '發行量加權股價指數'), None)
    if not target:
        # Some RWD versions put the index in a table with a slightly different label.
        target=next((r for r in rows if '發行量加權' in str(r.get('指數') or r.get('IndexName') or '')), None)
    if not target: raise RuntimeError('TAIEX row not found')
    close=num(target.get('收盤指數') or target.get('ClosingIndex'))
    change=num(target.get('漲跌點數') or target.get('Change'))
    pct=num(target.get('漲跌百分比') or target.get('ChangePercent'))
    return {'close':close,'change':change,'pct':pct}


def main():
    stocks=stock_data(); idx=index_data()
    valid=[s for s in stocks if s['close']>0]
    up=sum(s['change']>0 for s in valid); down=sum(s['change']<0 for s in valid); unchanged=len(valid)-up-down
    turnover=sum(s['value'] for s in valid)
    gainers=sorted(valid,key=lambda s:s['pct'],reverse=True)[:10]
    losers=sorted(valid,key=lambda s:s['pct'])[:10]
    active=sorted(valid,key=lambda s:s['value'],reverse=True)[:10]
    watch=[s for s in valid if s['code'] in {'0050','2330','2317','2454','2308','2382'}]
    payload={'generated_at':'2026-08-21T14:40:00+08:00','trade_date':ISO,'source':'TWSE official RWD historical API','market':{'stocks':len(valid),'up':up,'down':down,'unchanged':unchanged,'turnover':turnover,'turnover_billion':turnover/1e8,'index':{'close':idx['close'],'change':idx['change'],'pct':idx['pct']}},'trend':{'score':50,'label':'待分析','reasons':['已完成 2026-08-21 全市場收盤資料回補。'],'history_days':1,'ret5':None,'ret20':None},'watchlist':watch,'gainers':gainers,'losers':losers,'active':active,'sectors_up':[],'sectors_down':[],'margin':{},'news':[],'stocks':valid,'notes':['2026-08-21 為指定歷史收盤日。','股票資料來自 TWSE 官方歷史 RWD API。']}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'2026-08-21.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'latest.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Backfilled {ISO}: {len(valid)} stocks, turnover={turnover/1e8:.1f}億')

if __name__=='__main__': main()
