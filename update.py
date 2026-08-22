#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a Taiwan stock market snapshot from official TWSE OpenAPI data."""
from __future__ import annotations
import json, os, re, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
ROOT=Path(__file__).resolve().parent; DOCS=ROOT/'docs'; DATA_DIR=DOCS/'data'; HISTORY_PATH=DATA_DIR/'history.json'; LATEST_PATH=DATA_DIR/'latest.json'
BASE='https://openapi.twse.com.tw/v1'
ENDPOINTS={'index':f'{BASE}/exchangeReport/MI_INDEX','stocks':f'{BASE}/exchangeReport/STOCK_DAY_ALL','margin':f'{BASE}/exchangeReport/MI_MARGN','news':f'{BASE}/news/newsList'}
WATCHLIST=['0050','2330','2317','2454','2308','2382']; TAIPEI=timezone(timedelta(hours=8))
def get_json(url, attempts=3, timeout=30):
    last=None
    for i in range(attempts):
        try:
            req=Request(url,headers={'User-Agent':'taiwan-market-dashboard/1.0'})
            with urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8-sig'))
        except (HTTPError,URLError,TimeoutError,json.JSONDecodeError) as e:
            last=e
            if i+1<attempts:time.sleep(2**i)
    raise RuntimeError(f'API failed: {url}: {last}')
def records(payload):
    if isinstance(payload,list):return [x for x in payload if isinstance(x,dict)]
    if not isinstance(payload,dict):return []
    data,fields=payload.get('data'),payload.get('fields')
    if isinstance(data,list) and isinstance(fields,list):return [dict(zip(fields,row)) for row in data if isinstance(row,list)]
    if isinstance(data,list):return [x for x in data if isinstance(x,dict)]
    return []
def num(v):
    if v is None:return None
    s=str(v).strip().replace(',','')
    if s in {'','--','-','X','除權息','不比價'}:return None
    try:return float(s)
    except ValueError:return None
def first_num(d,*keys):
    for k in keys:
        if k in d:
            n=num(d[k])
            if n is not None:return n
    return None
def roc_to_iso(v):
    s=re.sub(r'\D','',str(v or ''))
    if len(s)!=7:return None
    try:return f'{int(s[:3])+1911:04d}-{int(s[3:5]):02d}-{int(s[5:]):02d}'
    except ValueError:return None
def parse_index(payload):
    target=next((r for r in records(payload) if str(r.get('指數',''))=='發行量加權股價指數'),None)
    if not target:raise RuntimeError('TWSE MI_INDEX missing TAIEX')
    date=roc_to_iso(target.get('日期') or target.get('Date')); close=first_num(target,'收盤指數'); change=first_num(target,'漲跌點數'); pct=first_num(target,'漲跌百分比')
    if not date or close is None:raise RuntimeError('TWSE MI_INDEX has no usable date/index')
    return {'date':date,'close':close,'change':change,'pct':pct}
def parse_stocks(payload):
    out=[]
    for r in records(payload):
        code=str(r.get('證券代號') or r.get('Code') or '').strip(); name=str(r.get('證券名稱') or r.get('Name') or '').strip(); close=first_num(r,'收盤價','Close'); change=first_num(r,'漲跌價','漲跌','Change'); volume=first_num(r,'成交股數','成交量','Volume'); value=first_num(r,'成交金額','Turnover','Value')
        if not code or not name or close is None or change is None:continue
        prev=close-change; pct=change/prev*100 if prev else 0
        out.append({'code':code,'name':name,'close':close,'change':change,'pct':pct,'volume':volume or 0,'value':value or 0})
    return out
def parse_margin(payload):
    for r in records(payload):
        if '融資餘額' in json.dumps(r,ensure_ascii=False) or '融券餘額' in json.dumps(r,ensure_ascii=False):
            return {str(k):n for k,v in r.items() if ('融資' in str(k) or '融券' in str(k)) and (n:=num(v)) is not None}
    return {}
def parse_news(payload):
    out=[]
    for r in records(payload):
        title=str(r.get('title') or r.get('標題') or r.get('新聞標題') or '').strip(); link=str(r.get('link') or r.get('url') or r.get('連結') or '').strip(); date=str(r.get('date') or r.get('日期') or r.get('發佈時間') or '').strip()
        if title:out.append({'title':title,'link':link,'date':date})
    return out[:12]
def load_history():
    if not HISTORY_PATH.exists():return []
    try:return json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
    except Exception:return []
def save_history(history):
    history=sorted({x['date']:x for x in history if 'date' in x}.values(),key=lambda x:x['date'])[-180:]; DATA_DIR.mkdir(parents=True,exist_ok=True); HISTORY_PATH.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding='utf-8')
def market_summary(stocks):
    valid=[s for s in stocks if s['close']>0]; up=sum(s['change']>0 for s in valid); down=sum(s['change']<0 for s in valid); return {'stocks':len(valid),'up':up,'down':down,'unchanged':len(valid)-up-down,'turnover':sum(s['value'] for s in valid)}
def trend_analysis(index,market,history):
    current={'date':index['date'],'index':index['close'],'turnover':market['turnover'],'up':market['up'],'down':market['down']}; hist=sorted({x['date']:x for x in history+[current]}.values(),key=lambda x:x['date']); recent=hist[-20:]; score=50; reasons=[]; den=market['up']+market['down']; breadth=market['up']/den if den else .5
    score += 15 if breadth>=.60 else 8 if breadth>=.52 else -8 if breadth<=.40 else -3 if breadth<=.48 else 0; reasons.append('上漲家數明顯多於下跌家數' if breadth>=.60 else '下跌家數明顯多於上漲家數' if breadth<=.40 else '漲跌家數接近，盤勢分歧')
    if index['pct'] is not None:score += 10 if index['pct']>=1 else 5 if index['pct']>0 else -5 if index['pct']<0 else 0; reasons.append(f"加權指數今日{'上漲' if index['pct']>0 else '下跌' if index['pct']<0 else '持平'} {abs(index['pct']):.2f}%")
    ret5=ret20=None
    if len(recent)>=5:
        ret5=(index['close']/recent[-5]['index']-1)*100 if recent[-5]['index'] else 0; score += 10 if ret5>1 else 5 if ret5>0 else -5 if ret5<-1 else 0; reasons.append(f'近5個交易日指數變動 {ret5:+.2f}%')
        avg=sum(x.get('turnover',0) for x in recent[:-1])/max(1,len(recent)-1)
        if avg:
            ratio=market['turnover']/avg; score += 5 if ratio>=1.2 else -3 if ratio<=.8 else 0; reasons.append(f'成交金額約為近4日平均的 {ratio:.2f} 倍')
    if len(recent)>=20:
        ret20=(index['close']/recent[0]['index']-1)*100 if recent[0]['index'] else 0; score += 10 if ret20>3 else 5 if ret20>0 else -5 if ret20<-3 else 0; reasons.append(f'近20個交易日指數變動 {ret20:+.2f}%')
    score=max(0,min(100,int(round(score)))); label='偏多' if score>=65 else '稍偏多' if score>=55 else '中性' if score>=45 else '稍偏空' if score>=35 else '偏空'; return {'score':score,'label':label,'reasons':reasons,'history_days':len(hist),'ret5':ret5,'ret20':ret20}
def main():
    now=datetime.now(TAIPEI); target=now.date().isoformat()
    if now.weekday()>=5 and os.getenv('FORCE_RUN')!='1':print(f'Weekend: {target}');return 0
    index=parse_index(get_json(ENDPOINTS['index']))
    if index['date']!=target:print(f"Market data not ready. Target={target}, TWSE={index['date']}");return 2
    stocks=parse_stocks(get_json(ENDPOINTS['stocks']))
    if len(stocks)<100:print(f'Stock data incomplete: {len(stocks)}');return 2
    market=market_summary(stocks); gainers=sorted(stocks,key=lambda s:s['pct'],reverse=True)[:10]; losers=sorted(stocks,key=lambda s:s['pct'])[:10]; active=sorted(stocks,key=lambda s:s['value'],reverse=True)[:10]; watch=[s for s in stocks if s['code'] in WATCHLIST]
    sectors=[]
    for r in records(get_json(ENDPOINTS['index'])):
        name=str(r.get('指數','')); pct=first_num(r,'漲跌百分比'); close=first_num(r,'收盤指數')
        if '類指數' in name and pct is not None and close is not None:sectors.append({'name':name,'pct':pct,'close':close})
    history=load_history(); trend=trend_analysis(index,market,history); save_history(history+[{'date':target,'index':index['close'],'index_pct':index['pct'],'turnover':market['turnover'],'up':market['up'],'down':market['down'],'unchanged':market['unchanged']}])
    try:news=parse_news(get_json(ENDPOINTS['news']))
    except Exception as e:print(f'News unavailable: {e}');news=[]
    try:margin=parse_margin(get_json(ENDPOINTS['margin']))
    except Exception as e:print(f'Margin unavailable: {e}');margin={}
    payload={'generated_at':now.isoformat(),'trade_date':target,'source':'TWSE OpenAPI','market':{**market,'turnover_billion':market['turnover']/1e8,'index':index},'trend':trend,'watchlist':watch,'gainers':gainers,'losers':losers,'active':active,'sectors_up':sorted(sectors,key=lambda x:x['pct'],reverse=True)[:8],'sectors_down':sorted(sectors,key=lambda x:x['pct'])[:8],'margin':margin,'news':news,'notes':['趨勢思考為規則式市場統計，不是買賣訊號，也不是投資建議。','目前資料範圍為 TWSE 上市市場；後續可加入 TPEX 上櫃、三大法人、財報與新聞情緒。']}; DATA_DIR.mkdir(parents=True,exist_ok=True); LATEST_PATH.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); print(f"Updated {target}: {len(stocks)} stocks, trend={trend['label']}({trend['score']})"); return 0
if __name__=='__main__':sys.exit(main())
