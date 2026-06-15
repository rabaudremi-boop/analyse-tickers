# -*- coding: utf-8 -*-
"""
chart_ta.py — Analyse technique « Max » d'un ticker -> graphique HTML interactif.

Génère un fichier .html autonome (librairie TradingView Lightweight Charts via CDN)
avec : bougies + EMA 20/50/200 + Bollinger + canal de régression + volume + POC/VA
+ supports/résistances + Fibonacci + pivots journaliers + figures, et deux panneaux
synchronisés RSI et MACD. Couches activables par cases à cocher.

Usage :
  python chart_ta.py "BINANCE:HYPEUSDT"
  python chart_ta.py "NASDAQ:AAPL" --days 365 --out aapl.html
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ta_core as ta
from fetch_ohlcv import fetch_ohlcv, display_name
from fetch_news import get_news

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _series(times, vals):
    return [{"time": times[i], "value": round(vals[i], 6)}
            for i in range(len(vals)) if vals[i] is not None]


def build_analysis(candles, meta, news=None, name=None, asset_meta=None):
    t = [c["time"] for c in candles]
    o = [c["open"] for c in candles]
    h = [c["high"] for c in candles]
    low = [c["low"] for c in candles]
    cl = [c["close"] for c in candles]
    vol = [c.get("volume", 0) for c in candles]
    cur = cl[-1]

    e20, e50, e200 = ta.ema(cl, 20), ta.ema(cl, 50), ta.ema(cl, 200)
    bb_mid, bb_up, bb_lo = ta.bollinger(cl, 20, 2)
    rsi = ta.rsi(cl, 14)
    macd_line, macd_sig, macd_hist = ta.macd(cl)
    atr = ta.atr(h, low, cl, 14)
    sup, res = ta.sr_zones(h, low, cur)
    fib, sh, slo = ta.fib_levels(h, low)
    pivots = ta.daily_pivots(h[-2], low[-2], cl[-2]) if len(cl) >= 2 else {}
    reg = ta.regression_channel(cl, 120)
    vp = ta.volume_profile(h, low, cl, vol)
    patterns = ta.detect_patterns(h, low, cl)
    for p in patterns:
        p["time"] = t[p["index"]]

    reg_series = {}
    if reg:
        rt = t[reg["start"]:]
        reg_series = {
            "mid": [{"time": rt[i], "value": reg["mid"][i]} for i in range(len(rt))],
            "up": [{"time": rt[i], "value": reg["upper"][i]} for i in range(len(rt))],
            "lo": [{"time": rt[i], "value": reg["lower"][i]} for i in range(len(rt))],
        }

    # lecture synthétique
    trend = "haussier" if cur > (e200[-1] or cur) else "baissier"
    rsi_last = next((v for v in reversed(rsi) if v is not None), None)
    rsi_state = ("suracheté" if rsi_last and rsi_last > 70
                 else "survendu" if rsi_last and rsi_last < 30 else "neutre")
    near_res = res[0]["price"] if res else sh
    near_sup = sup[0]["price"] if sup else slo

    # Score de biais technique (synthèse de signaux, PAS un conseil)
    score = ta.technical_score(
        cl, e20, e50, e200, rsi_last,
        macd_line[-1] if macd_line else None,
        macd_hist[-1] if macd_hist else None,
        bb_mid[-1] if bb_mid else None,
        sup, res, patterns, vp)

    # Zone d'achat potentielle (confluence de supports sous le prix)
    buy_zone = ta.ideal_buy_zone(
        cur, sup, fib, e50[-1] if e50 else None, e200[-1] if e200 else None,
        pivots, vp, atr[-1] if atr else None)

    readout = {
        "current": round(cur, 6),
        "trend": f"prix {'au-dessus' if trend == 'haussier' else 'sous'} EMA200 ({trend})",
        "rsi": rsi_last, "rsi_state": rsi_state,
        "atr": round(atr[-1], 6) if atr[-1] else None,
        "near_resistance": near_res, "near_support": near_sup,
        "patterns": [p["type"] for p in patterns],
        "stars": score["stars"], "bias": score["bias"], "score": score["score"],
    }

    am = asset_meta or {}
    return {
        "symbol": meta["input"], "name": name or meta["input"],
        "asset_class": meta["asset_class"],
        "sector": am.get("sector"), "desc": am.get("desc"),
        "interval": meta.get("interval", "1d"),
        "source": meta["source"], "generated_at": datetime.now(timezone.utc).isoformat(),
        "t": t, "o": o, "h": h, "l": low, "cl": cl, "vol": vol,
        "ema20": _series(t, e20), "ema50": _series(t, e50), "ema200": _series(t, e200),
        "bb_up": _series(t, bb_up), "bb_mid": _series(t, bb_mid), "bb_lo": _series(t, bb_lo),
        "rsi": _series(t, rsi),
        "macd_line": _series(t, macd_line), "macd_sig": _series(t, macd_sig),
        "macd_hist": [{"time": t[i], "value": round(macd_hist[i], 6),
                       "color": "#1D9E7588" if macd_hist[i] >= 0 else "#E24B4A88"}
                      for i in range(len(t))],
        "reg": reg_series,
        "sup": sup, "res": res, "fib": fib, "swing_high": sh, "swing_low": slo,
        "pivots": pivots, "vprofile": vp, "patterns": patterns,
        "score": score, "buy_zone": buy_zone, "news": news or [], "readout": readout,
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — analyse technique</title>
<style>
  :root{color-scheme:light dark}
  body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#fff;color:#1a1a1a}
  @media(prefers-color-scheme:dark){body{background:#0e0f12;color:#d8d8d8}}
  .wrap{max-width:1180px;margin:0 auto;padding:16px}
  h1{font-size:18px;font-weight:600;margin:0 0 2px}
  .sub{font-size:12px;opacity:.65;margin-bottom:10px}
  .read{font-size:13px;line-height:1.7;background:rgba(128,128,128,.08);border-radius:8px;padding:10px 14px;margin-bottom:12px}
  .read b{font-weight:600}
  .score{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px;padding:10px 14px;border-radius:8px;background:rgba(127,119,221,.10)}
  .stars{font-size:22px;letter-spacing:2px;color:#BA7517}
  .bias{font-size:15px;font-weight:600}
  .drivers{font-size:11px;opacity:.7}
  .buyzone{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px;padding:10px 14px;border-radius:8px;background:rgba(29,158,117,.12)}
  .bz-range{font-size:16px;font-weight:600;color:#0F6E56}
  @media(prefers-color-scheme:dark){.bz-range{color:#5DCAA5}}
  .news{font-size:13px;line-height:1.55}
  .news a{display:block;text-decoration:none;color:inherit;padding:7px 0;border-bottom:1px solid rgba(128,128,128,.12)}
  .news a:hover{opacity:.7}.news .meta{font-size:11px;opacity:.55}
  .nav{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
  .nav select{font-size:14px;padding:6px 10px;border-radius:8px;background:transparent;color:inherit;border:1px solid rgba(128,128,128,.4);max-width:340px}
  .nav button{font-size:13px;padding:5px 13px;border-radius:8px;border:1px solid rgba(128,128,128,.4);background:transparent;color:inherit;cursor:pointer}
  .nav button.active{background:#378ADD;color:#fff;border-color:#378ADD}
  .nav .lab{font-size:12px;opacity:.6}
  .adesc{font-size:13px;line-height:1.5;background:rgba(128,128,128,.07);border-radius:8px;padding:9px 13px;margin-bottom:12px}
  .adesc .sec{display:inline-block;font-size:11px;font-weight:600;color:#534AB7;background:rgba(127,119,221,.15);border-radius:6px;padding:1px 8px;margin-right:8px}
  @media(prefers-color-scheme:dark){.adesc .sec{color:#AFA9EC}}
  .analysis{background:rgba(128,128,128,.06);border-radius:10px;padding:14px 18px;margin-bottom:16px;font-size:14px;line-height:1.65}
  .analysis h1,.analysis h2,.analysis h3{font-size:16px;font-weight:600;margin:14px 0 6px}
  .analysis h1{font-size:18px}
  .analysis table{border-collapse:collapse;width:100%;margin:8px 0;font-size:13px}
  .analysis th,.analysis td{border:1px solid rgba(128,128,128,.25);padding:5px 9px;text-align:left}
  .analysis code{background:rgba(128,128,128,.15);padding:1px 5px;border-radius:4px;font-size:13px}
  .analysis .muted{opacity:.6;font-style:italic}
  .analysis details summary{cursor:pointer;font-weight:600;font-size:15px}
  .toggles{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:10px;font-size:12px}
  .toggles label{display:flex;align-items:center;gap:5px;cursor:pointer;user-select:none}
  .legend{display:flex;flex-wrap:wrap;gap:12px;font-size:11px;opacity:.8;margin:4px 0 8px}
  .legend i{width:14px;height:2px;display:inline-block;vertical-align:middle;margin-right:4px}
  .pane{width:100%}
  .lbl{font-size:11px;opacity:.6;margin:8px 0 2px}
  .disc{font-size:11px;opacity:.55;margin-top:14px}
</style></head>
<body><div class="wrap">
  <div class="nav" id="nav" style="display:none">
    <span class="lab">Actif :</span><select id="navsel"></select>
    <span class="lab">vue :</span>
    <button id="b1d" data-iv="1d">1D</button><button id="b1w" data-iv="1w">1W</button>
  </div>
  <h1 id="ttl"></h1><div class="sub" id="sub"></div>
  <div class="adesc" id="adesc"></div>
  <div class="score" id="score"></div>
  <div class="buyzone" id="bz"></div>
  <div class="read" id="read"></div>
  <details class="analysis" id="analysis" open><summary>📋 Analyse complète (skill)</summary>__ANALYSIS__</details>
  <div class="toggles" id="tg"></div>
  <div class="legend" id="lg"></div>
  <div class="lbl">Prix</div><div id="main" class="pane" style="height:430px"></div>
  <div class="lbl">RSI (14)</div><div id="rsi" class="pane" style="height:120px"></div>
  <div class="lbl">MACD (12,26,9)</div><div id="macd" class="pane" style="height:130px"></div>
  <div class="lbl">Actualités récentes</div><div class="news" id="news"></div>
  <div class="disc">Note ⭐ = synthèse automatique des signaux techniques (biais haussier/baissier). La « zone d'achat potentielle » est une zone de <b>confluence de supports</b> (technique), <b>pas un signal ni un conseil d'achat/vente</b>. Niveaux tracés automatiquement. Source données : __SUB__ · actualités : Yahoo/Google News.</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script>
const D = __DATA__;
const NAV = null; /*NAVSLOT*/
const CURRENT = __CURRENT__;
function buildNav(){
  if(!NAV || !NAV.length) return;
  const navEl=document.getElementById('nav'); navEl.style.display='flex';
  const sel=document.getElementById('navsel');
  NAV.forEach(it=>{const o=document.createElement('option');o.value=it.name;o.textContent=it.name;if(it.name===CURRENT.name)o.selected=true;sel.appendChild(o);});
  sel.addEventListener('change',()=>{const it=NAV.find(x=>x.name===sel.value);if(it&&it[CURRENT.interval])location.href=it[CURRENT.interval];});
  const cur=NAV.find(x=>x.name===CURRENT.name)||{};
  ['1d','1w'].forEach(iv=>{const b=document.getElementById('b'+iv);if(!b)return;if(CURRENT.interval===iv)b.classList.add('active');b.addEventListener('click',()=>{if(cur[iv])location.href=cur[iv];});});
}
buildNav();
function go(){
  if(!window.LightweightCharts){return setTimeout(go,120);}
  const LC=LightweightCharts, dark=matchMedia&&matchMedia('(prefers-color-scheme:dark)').matches;
  document.getElementById('ttl').textContent=(D.name||D.symbol)+'  ·  '+(D.interval||'1d').toUpperCase();
  document.getElementById('sub').textContent=D.symbol+' · '+(D.sector||D.asset_class)+' · '+D.source+' · généré '+D.generated_at.slice(0,16).replace('T',' ')+' UTC';
  var ad=document.getElementById('adesc');
  if(D.desc){ad.innerHTML=(D.sector?'<span class="sec">'+D.sector+'</span>':'')+D.desc;}else{ad.style.display='none';}
  const r=D.readout;
  document.getElementById('read').innerHTML=
    '<b>Lecture :</b> '+r.trend+' · RSI '+(r.rsi?r.rsi.toFixed(0):'n/a')+' ('+r.rsi_state+')'
    +' · ATR '+(r.atr??'n/a')+'<br><b>Résistance proche :</b> '+r.near_resistance
    +' · <b>Support proche :</b> '+r.near_support
    +(r.patterns.length?' · <b>Figures :</b> '+r.patterns.join(', '):'');
  const sc=D.score, full='★'.repeat(sc.stars)+'☆'.repeat(5-sc.stars);
  document.getElementById('score').innerHTML=
    '<span class="stars">'+full+'</span><span class="bias">'+sc.bias+'</span>'
    +'<span class="drivers">score '+(sc.score>=0?'+':'')+sc.score+' · '+sc.drivers.slice(0,4).join(' · ')+'</span>';
  const nv=document.getElementById('news');
  if(D.news&&D.news.length){nv.innerHTML=D.news.map(function(a){
    return '<a href="'+a.link+'" target="_blank" rel="noopener">'+a.title
      +'<span class="meta"> — '+(a.source||'')+(a.date?' · '+a.date:'')+'</span></a>';}).join('');}
  else{nv.innerHTML='<div class="meta">Pas d\'actualité récupérée.</div>';}
  document.getElementById('lg').innerHTML=
    '<span><i style="background:#378ADD"></i>EMA20</span><span><i style="background:#BA7517"></i>EMA50</span>'
    +'<span><i style="background:#7F77DD"></i>EMA200</span><span><i style="border-top:2px dashed #E24B4A;height:0"></i>Résist.</span>'
    +'<span><i style="border-top:2px dashed #1D9E75;height:0"></i>Support</span><span><i style="border-top:1px dotted #BA7517;height:0"></i>Fib</span>'
    +'<span><i style="border-top:1px dotted #888;height:0"></i>Pivots</span><span><i style="background:#7F77DD"></i>POC</span>';

  const opts=(h)=>({height:h,layout:{background:{type:'solid',color:'transparent'},textColor:dark?'#9aa0a6':'#444'},
    grid:{vertLines:{color:'rgba(128,128,128,.07)'},horzLines:{color:'rgba(128,128,128,.07)'}},
    rightPriceScale:{borderColor:'rgba(128,128,128,.18)'},timeScale:{borderColor:'rgba(128,128,128,.18)',timeVisible:false},
    crosshair:{mode:0},autoSize:true});
  const main=LC.createChart(document.getElementById('main'),opts(430));
  const rsiC=LC.createChart(document.getElementById('rsi'),opts(120));
  const macdC=LC.createChart(document.getElementById('macd'),opts(130));

  const cs=main.addCandlestickSeries({upColor:'#1D9E75',downColor:'#E24B4A',borderVisible:false,wickUpColor:'#1D9E75',wickDownColor:'#E24B4A'});
  cs.setData(D.t.map((t,i)=>({time:t,open:D.o[i],high:D.h[i],low:D.l[i],close:D.cl[i]})));
  // volume (échelle dédiée en bas)
  const vs=main.addHistogramSeries({priceScaleId:'vol',priceFormat:{type:'volume'},color:'#8884'});
  vs.setData(D.t.map((t,i)=>({time:t,value:D.vol[i],color:(D.cl[i]>=D.o[i]?'#1D9E7544':'#E24B4A44')})));
  main.priceScale('vol').applyOptions({scaleMargins:{top:0.82,bottom:0}});

  const mkLine=(c,parent,arr,color,w,style)=>{const s=parent.addLineSeries({color,lineWidth:w||1.5,lineStyle:style||0,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});s.setData(arr);return s;};
  const G={};
  G.ema=[mkLine(0,main,D.ema20,'#378ADD'),mkLine(0,main,D.ema50,'#BA7517'),mkLine(0,main,D.ema200,'#7F77DD')];
  G.boll=[mkLine(0,main,D.bb_up,'#888',1,2),mkLine(0,main,D.bb_mid,'#8886',1,2),mkLine(0,main,D.bb_lo,'#888',1,2)];
  G.reg=[];
  if(D.reg&&D.reg.mid){G.reg=[mkLine(0,main,D.reg.mid,'#37b',1.5,0),mkLine(0,main,D.reg.up,'#37b8',1,2),mkLine(0,main,D.reg.lo,'#37b8',1,2)];}

  // price lines groupées (S/R, fib, pivots, vol profile)
  const PL={sr:[],fib:[],piv:[],vp:[]};
  const addPL=(group,price,color,style,title)=>{PL[group].push(cs.createPriceLine({price,color,lineWidth:1,lineStyle:style,axisLabelVisible:true,title}));};
  const cfgPL={sr:[],fib:[],piv:[],vp:[]};
  D.sup.forEach(z=>cfgPL.sr.push([z.price,'#1D9E75',2,'S '+z.price]));
  D.res.forEach(z=>cfgPL.sr.push([z.price,'#E24B4A',2,'R '+z.price]));
  Object.entries(D.fib).forEach(([k,v])=>cfgPL.fib.push([v,'#BA751799',1,'fib '+k]));
  Object.entries(D.pivots).forEach(([k,v])=>cfgPL.piv.push([v,'#88888899',1,k]));
  if(D.vprofile){cfgPL.vp.push([D.vprofile.poc,'#7F77DD',0,'POC']);cfgPL.vp.push([D.vprofile.vah,'#7F77DD88',2,'VAH']);cfgPL.vp.push([D.vprofile.val,'#7F77DD88',2,'VAL']);}
  const drawPL=(g)=>{cfgPL[g].forEach(c=>addPL(g,c[0],c[1],c[2],c[3]));};
  const clearPL=(g)=>{PL[g].forEach(l=>cs.removePriceLine(l));PL[g]=[];};
  ['sr','fib','piv','vp'].forEach(drawPL);

  // zone d'achat potentielle (confluence de supports)
  const fmt=x=>(+x).toLocaleString('fr-FR',{maximumSignificantDigits:5});
  const bz=D.buy_zone, bzel=document.getElementById('bz');
  if(bz){
    bzel.innerHTML='<span style="font-size:13px">🎯 <b>Zone d\'achat potentielle</b> (confluence de supports) :</span>'
      +'<span class="bz-range">'+fmt(bz.low)+' – '+fmt(bz.high)+'</span>'
      +'<span class="drivers">à '+bz.distance_pct+'% sous le cours · '+bz.components.slice(0,5).join(', ')+'</span>';
    cs.createPriceLine({price:bz.high,color:'#1D9E75',lineWidth:2,lineStyle:0,axisLabelVisible:true,title:'🎯 zone achat ↑'});
    cs.createPriceLine({price:bz.low,color:'#1D9E75',lineWidth:2,lineStyle:0,axisLabelVisible:true,title:'🎯 zone achat ↓'});
  } else { bzel.style.display='none'; }

  // marqueurs de figures
  if(D.patterns.length){cs.setMarkers(D.patterns.map(p=>({time:p.time,position:'aboveBar',color:'#7F77DD',shape:'circle',text:p.type.split(' ')[0]})));}

  // RSI pane
  mkLine(0,rsiC,D.rsi,'#7F77DD',1.5,0);
  const rsiSpan=D.t.length?[{time:D.t[0]},{time:D.t[D.t.length-1]}]:[];
  [70,50,30].forEach(lv=>{const s=rsiC.addLineSeries({color:lv===50?'#8884':'#8886',lineWidth:1,lineStyle:lv===50?0:2,lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false});s.setData(D.t.map(t=>({time:t,value:lv})));});
  // MACD pane
  const mh=macdC.addHistogramSeries({priceLineVisible:false,lastValueVisible:false});
  mh.setData(D.macd_hist);
  mkLine(0,macdC,D.macd_line,'#378ADD',1.5,0);
  mkLine(0,macdC,D.macd_sig,'#E24B4A',1.5,0);

  // sync des 3 échelles de temps (garde anti-rebond pour éviter la boucle de rendu)
  const charts=[main,rsiC,macdC];
  let applying=false;
  charts.forEach(src=>src.timeScale().subscribeVisibleLogicalRangeChange(rg=>{
    if(applying||!rg)return;
    applying=true;
    charts.forEach(o=>{
      if(o===src)return;
      const cur=o.timeScale().getVisibleLogicalRange();
      if(!cur||Math.abs(cur.from-rg.from)>0.5||Math.abs(cur.to-rg.to)>0.5){
        o.timeScale().setVisibleLogicalRange(rg);
      }
    });
    requestAnimationFrame(()=>{applying=false;});
  }));
  main.timeScale().fitContent();

  // toggles
  const groups=[['ema','EMA',true],['boll','Bollinger',true],['reg','Régression',true],
                ['sr','S/R',true],['fib','Fibonacci',true],['piv','Pivots',false],['vp','Vol profile',true]];
  const tg=document.getElementById('tg');
  groups.forEach(([key,label,on])=>{
    const id='t_'+key;
    tg.insertAdjacentHTML('beforeend',`<label><input type="checkbox" id="${id}" ${on?'checked':''}>${label}</label>`);
  });
  const apply=(key,vis)=>{
    if(['ema','boll','reg'].includes(key)){(G[key]||[]).forEach(s=>s.applyOptions({visible:vis}));}
    else{if(vis)drawPL(key);else clearPL(key);}
  };
  groups.forEach(([key,,on])=>{
    const el=document.getElementById('t_'+key);
    if(!on)apply(key,false);
    el.addEventListener('change',e=>apply(key,e.target.checked));
  });
}
go();
</script></body></html>"""


def render_html(data, analysis_html=""):
    title = data.get("name", data["symbol"])
    current = {"name": data.get("name", data["symbol"]), "interval": data.get("interval", "1d")}
    return (HTML_TEMPLATE
            .replace("__DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__CURRENT__", json.dumps(current, ensure_ascii=False))
            .replace("__ANALYSIS__", analysis_html or "")
            .replace("__TITLE__", title)
            .replace("__SUB__", data["source"]))


def _analysis_key(tv_symbol):
    return re.sub(r"[^A-Za-z0-9]+", "_", tv_symbol.strip().upper()).strip("_")


def load_analysis_html(tv_symbol, name, analysis_dir):
    """Charge analysis/<clé>.md (Markdown -> HTML) si présent, sinon placeholder."""
    placeholder = (f'<p class="muted">Analyse non encore générée. '
                   f'Lance « analyse {name} » dans Claude Code pour la remplir.</p>')
    if not analysis_dir:
        return placeholder
    path = os.path.join(analysis_dir, _analysis_key(tv_symbol) + ".md")
    if not os.path.exists(path):
        return placeholder
    try:
        import markdown
        with open(path, encoding="utf-8") as f:
            md = f.read()
        return markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    except Exception:
        try:
            with open(path, encoding="utf-8") as f:
                return "<pre>" + f.read() + "</pre>"
        except OSError:
            return placeholder


def analyze_to_html(tv_symbol, days, out_path, with_news=True, interval="1d",
                    analysis_dir=None, asset_meta=None):
    candles, meta = fetch_ohlcv(tv_symbol, days, interval)
    if not candles:
        return None, meta
    if len(candles) < 30:
        meta["error"] = f"trop peu de bougies ({len(candles)})"
        return None, meta
    news = get_news(meta["asset_class"], meta["resolved"]) if with_news else []
    name = display_name(meta["asset_class"], meta["resolved"])
    data = build_analysis(candles, meta, news=news, name=name, asset_meta=asset_meta)
    analysis_html = load_analysis_html(tv_symbol, name, analysis_dir)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(render_html(data, analysis_html))
    return data, meta


def main():
    ap = argparse.ArgumentParser(description="Analyse technique -> graphique HTML.")
    ap.add_argument("symbol", help="Symbole TradingView, ex. BINANCE:HYPEUSDT")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--interval", choices=["1d", "1w"], default="1d", help="Unité de temps")
    ap.add_argument("--out", help="Chemin HTML de sortie")
    ap.add_argument("--no-news", action="store_true", help="Ne pas récupérer les actualités")
    ap.add_argument("--analysis-dir", help="Dossier des analyses Markdown (analysis/<clé>.md)")
    args = ap.parse_args()

    safe = args.symbol.replace(":", "_").replace("/", "_")
    out = args.out or os.path.join(os.getcwd(), f"{safe}_{args.interval}.html")
    data, meta = analyze_to_html(args.symbol, args.days, out,
                                 with_news=not args.no_news, interval=args.interval,
                                 analysis_dir=args.analysis_dir)
    if not data:
        print(f"ÉCHEC {args.symbol} : {meta.get('error')}", file=sys.stderr)
        sys.exit(1)
    if not args.out:  # renomme avec le nom lisible de l'actif
        import re as _re
        nice = _re.sub(r"[^A-Za-z0-9_.-]", "_", data.get("name", safe))[:40]
        new_out = os.path.join(os.path.dirname(out), f"{nice}_{args.interval}.html")
        if new_out != out:
            os.replace(out, new_out)
            out = new_out
    r = data["readout"]
    rsi_txt = f"{r['rsi']:.0f}" if r['rsi'] else "n/a"
    stars = "★" * r["stars"] + "☆" * (5 - r["stars"])
    print(f"OK {meta['input']} [{meta['asset_class']}] {stars} {r['bias']} "
          f"(score {r['score']:+.1f}) | RSI {rsi_txt} | "
          f"S {r['near_support']} R {r['near_resistance']} | news {len(data['news'])}",
          file=sys.stderr)
    print(out)


if __name__ == "__main__":
    main()
