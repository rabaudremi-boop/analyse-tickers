# -*- coding: utf-8 -*-
"""
batch_charts.py — Analyse technique en lot d'une watchlist TradingView.

Entrée :
  - un fichier d'export TradingView (.txt) : clic droit sur la liste -> "Export watchlist"
    (format : symboles séparés par des virgules / retours ligne, sections en ###),
  - OU --symbols "BINANCE:BTCUSDT,NASDAQ:AAPL,..."

Sortie : un dossier avec un .html par ticker + un index.html récapitulatif
(tendance, RSI, support/résistance proches, figures) avec recherche.

Usage :
  python batch_charts.py ma_watchlist.txt
  python batch_charts.py --symbols "BINANCE:HYPEUSDT,NASDAQ:AAPL" --out ./charts
"""
import argparse
import json
import os
import sys
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_ta import analyze_to_html
from fetch_ohlcv import resolve, display_name
import pwa

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def parse_watchlist(text):
    """Extrait (symbole, catégorie) d'une watchlist. Lignes "SYM" ou "SYM|Catégorie".
    Gère aussi l'export TradingView (virgules, sections ###)."""
    out, seen = [], set()
    for tok in re.split(r"[,\n\r]+", text):
        tok = tok.strip()
        if not tok or tok.startswith("###"):
            continue
        if "|" in tok:
            sym, cat = tok.split("|", 1)
            sym, cat = sym.strip(), cat.strip()
        else:
            sym, cat = tok, ""
        if sym.upper() in seen:
            continue
        seen.add(sym.upper())
        out.append((sym, cat))
    return out


def safe_name(sym):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", sym)


CAT_FROM_CLASS = {"crypto": "Crypto", "commodity": "Matière première",
                  "forex": "Devise", "index": "Indice", "stock": "Action"}


def risk_reward(r):
    """Ratio risque/récompense TECHNIQUE : récompense (vers résistance) vs risque
    (vers le BAS de la zone d'achat = stop réel ; sinon support). Ajusté biais+RSI.
    rr plafonné à 6 ; opp = score d'opportunité de classement."""
    out = {"rr_ratio": None, "upside": None, "downside": None, "opp": -99}
    try:
        cur, res = float(r.get("current")), float(r.get("resistance"))
    except (TypeError, ValueError):
        return out
    bz = r.get("buy_zone") or {}
    stop = bz.get("low")
    if stop is None:
        try:
            stop = float(r.get("support"))
        except (TypeError, ValueError):
            return out
    if not (stop and stop < cur < res):
        return out
    upside = (res - cur) / cur * 100
    downside = (cur - stop) / cur * 100
    out["upside"], out["downside"] = round(upside, 1), round(downside, 1)
    if downside <= 0.3:  # garde-fou : stop trop proche -> non pertinent
        return out
    rr = min(upside / downside, 6.0)
    out["rr_ratio"] = round(rr, 2)
    bias = r.get("bias", "") or ""
    bf = 1.25 if "haussier" in bias else (0.75 if "baissier" in bias else 1.0)
    rsi = r.get("rsi") or 50
    rp = 0.8 if rsi > 72 else (1.15 if rsi < 35 else 1.0)
    out["opp"] = round(rr * bf * rp, 2)
    return out


def run_one(sym, days, out_dir, with_news=True, intervals=("1d", "1w"),
            analysis_dir=None, category=""):
    files = {}
    primary = None
    last_err = None
    for idx, iv in enumerate(intervals):
        tmp = os.path.join(out_dir, safe_name(sym) + f"_{iv}.html")
        try:
            data, meta = analyze_to_html(sym, days, tmp,
                                         with_news=(with_news and idx == 0), interval=iv,
                                         analysis_dir=analysis_dir)
        except Exception as e:
            data, meta, last_err = None, None, f"{type(e).__name__}: {e}"
        if data:
            # nom lisible + clé symbole -> garantit l'unicité (évite collisions de noms tronqués)
            nice = (safe_name(data.get("name", sym))[:30].strip("_") or "x") + "_" + safe_name(sym)
            fn = os.path.join(out_dir, f"{nice}_{iv}.html")
            if fn != tmp:
                os.replace(tmp, fn)
            files[iv] = os.path.basename(fn)
            if primary is None:
                primary = (data, meta)
        elif meta:
            last_err = meta.get("error")
    if not primary:
        return {"symbol": sym, "ok": False, "error": last_err or "échec"}
    data, meta = primary
    r = data["readout"]
    cat = category or CAT_FROM_CLASS.get(meta["asset_class"], "Action")
    return {"symbol": sym, "ok": True, "files": files, "name": data.get("name", sym),
            "asset": meta["asset_class"], "category": cat, "trend": r["trend"], "rsi": r["rsi"],
            "rsi_state": r["rsi_state"], "support": r["near_support"],
            "resistance": r["near_resistance"], "patterns": r["patterns"],
            "current": r["current"], "stars": r["stars"], "bias": r["bias"],
            "score": r["score"],
            "top_news": data["news"][0]["title"] if data.get("news") else "",
            "buy_zone": data.get("buy_zone")}


INDEX_TPL = r"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>__TITLE__</title>
<style>
:root{--ac:#378ADD;--bg:#f5f6f8;--surf:#fff;--bd:#e6e8ec;--tx:#10131a;--mut:#6b7280;color-scheme:light dark}
@media(prefers-color-scheme:dark){:root{--bg:#0c0d11;--surf:#16181d;--bd:#23262d;--tx:#e6e8ec;--mut:#9aa0a6}}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:var(--bg);color:var(--tx);padding-bottom:78px}
.wrap{max-width:1180px;margin:0 auto;padding:18px 16px}
.hd{display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap}
h1{font-size:22px;font-weight:700;margin:0}
.sub{font-size:12px;color:var(--mut);margin:2px 0 14px}
.panel{background:var(--surf);border:1px solid var(--bd);border-radius:16px;padding:16px;margin-bottom:14px}
.panel h2{font-size:12px;font-weight:600;margin:0 0 12px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px}
.stat{flex:1;min-width:80px;background:var(--bg);border-radius:12px;padding:10px 12px}
.stat .v{font-size:24px;font-weight:700;line-height:1}.stat .l{font-size:11px;color:var(--mut);margin-top:3px}
.chips{display:flex;flex-wrap:wrap;gap:7px}
.chip{font-size:12px;padding:5px 10px;border-radius:9px;background:var(--bg);white-space:nowrap}
.chip b{font-weight:600}
.lead{font-size:12px;color:var(--mut);margin-top:10px;line-height:1.5}
input{width:100%;max-width:320px;padding:10px 13px;border:1px solid var(--bd);border-radius:10px;font-size:14px;background:var(--surf);color:inherit}
.fbar{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin:12px 0}
.fbtn{font-size:12px;padding:6px 12px;border-radius:9px;border:1px solid var(--bd);background:var(--surf);color:inherit;cursor:pointer;transition:.12s}
.fbtn.active{background:var(--ac);color:#fff;border-color:var(--ac)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.card{position:relative;color:inherit;background:var(--surf);border:1px solid var(--bd);border-radius:14px;padding:13px 15px;transition:.12s}
.card:hover{border-color:var(--ac);transform:translateY(-1px)}
.fav{position:absolute;top:10px;right:10px;border:none;background:none;font-size:19px;line-height:1;cursor:pointer;color:#c9ad5a;padding:2px}
.fav.on{color:#e8b923}
.sym{font-size:15px;font-weight:700;padding-right:24px}
.tag{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.03em;margin-top:1px}
.row{font-size:12px;margin-top:6px;color:var(--tx);opacity:.92}
.up{color:#1D9E75}.down{color:#E24B4A}
.stars{font-size:14px;color:#e8b923;letter-spacing:1px;margin-top:7px}
.biasl{font-size:11px;color:var(--mut);letter-spacing:0}
.rr{display:inline-block;font-size:12px;margin-top:7px;font-weight:700;padding:2px 8px;border-radius:7px}
.rr small{font-weight:400;opacity:.8}
.rr-good{background:rgba(29,158,117,.15);color:#0F6E56}.rr-mid{background:rgba(186,117,23,.15);color:#8a5a12}.rr-bad{background:rgba(226,75,74,.13);color:#a32d2d}
@media(prefers-color-scheme:dark){.rr-good{color:#5DCAA5}.rr-mid{color:#EF9F27}.rr-bad{color:#F09595}}
.bz{font-size:11px;margin-top:7px;color:#0F6E56;background:rgba(29,158,117,.12);border-radius:7px;padding:3px 8px;display:inline-block}
@media(prefers-color-scheme:dark){.bz{color:#5DCAA5}}
.news1{font-size:11px;color:var(--mut);margin-top:7px;line-height:1.4}
.pill{display:inline-block;font-size:10px;padding:2px 8px;border-radius:10px;background:rgba(127,119,221,.15);color:#534AB7;margin-top:7px}
@media(prefers-color-scheme:dark){.pill{color:#AFA9EC}}
.tflinks{margin-top:10px;font-size:12px}
.tflinks a{color:var(--ac);text-decoration:none;font-weight:600;border:1px solid var(--ac);border-radius:8px;padding:3px 11px;margin-right:6px;display:inline-block}
.tflinks a:active{background:var(--ac);color:#fff}
.err{opacity:.55;border-style:dashed}
.empty{text-align:center;color:var(--mut);padding:50px 20px;font-size:14px}
.infos{background:var(--surf);border:1px solid var(--bd);border-radius:16px;padding:18px;font-size:13px;line-height:1.7}
.infos h3{margin:0 0 6px;font-size:15px}
.tabbar{position:fixed;left:0;right:0;bottom:0;display:flex;background:var(--surf);border-top:1px solid var(--bd);padding-bottom:env(safe-area-inset-bottom);z-index:50}
.tb{flex:1;border:none;background:none;color:var(--mut);font-size:10px;padding:9px 4px 8px;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:3px;font-family:inherit}
.tb .ic{font-size:19px;line-height:1}
.tb.active{color:var(--ac)}
</style></head><body><div class="wrap">
<div class="hd"><h1>__TITLE__</h1><span class="sub">__N__ actifs · MAJ __DATE__ UTC</span></div>
<div id="panel">__PANEL__</div>
<div class="fbar" id="filterbar">
  <input id="q" placeholder="rechercher un actif…" oninput="flt()">
  <span id="catf"></span>
</div>
<div class="fbar" id="biasf"></div>
<div class="grid" id="g">__CARDS__</div>
<div class="empty" id="emptyfav" style="display:none">Aucun actif en surveillance.<br>Touche l'étoile ☆ sur une carte pour l'ajouter.</div>
<div class="infos" id="infos" style="display:none">__INFOS__</div>
</div>
<nav class="tabbar">
  <button class="tb active" data-tab="marche" onclick="setTab('marche')"><span class="ic">📊</span>Marché</button>
  <button class="tb" data-tab="surveillance" onclick="setTab('surveillance')"><span class="ic">⭐</span>Surveillance</button>
  <button class="tb" data-tab="top" onclick="setTab('top')"><span class="ic">🎯</span>Top R/R</button>
  <button class="tb" data-tab="infos" onclick="setTab('infos')"><span class="ic">ℹ️</span>Infos</button>
</nav>
<script>
var CATS=__CATS__, curCat='Tous', curBias='Tous', tab='marche';
var FAV=JSON.parse(localStorage.getItem('ta-favs')||'[]');
function saveFav(){localStorage.setItem('ta-favs',JSON.stringify(FAV));}
function toggleFav(s,btn){event.stopPropagation();var i=FAV.indexOf(s);if(i>=0)FAV.splice(i,1);else FAV.push(s);saveFav();markFavs();if(tab==='surveillance')flt();}
function markFavs(){document.querySelectorAll('#g .card').forEach(function(c){var b=c.querySelector('.fav');if(!b)return;var f=FAV.indexOf(c.dataset.sym)>=0;b.textContent=f?'★':'☆';b.classList.toggle('on',f);});}
function chips(id,list,cur,setter){var e=document.getElementById(id);e.innerHTML='';list.forEach(function(c){var b=document.createElement('button');b.className='fbtn'+(c===cur?' active':'');b.textContent=c;b.onclick=function(){setter(c);};e.appendChild(b);});}
function renderChips(){chips('catf',['Tous'].concat(CATS),curCat,function(c){curCat=c;renderChips();flt();});chips('biasf',['Tous','Haussier','Baissier','Neutre'],curBias,function(c){curBias=c;renderChips();flt();});}
function setTab(t){tab=t;document.querySelectorAll('.tabbar .tb').forEach(function(b){b.classList.toggle('active',b.dataset.tab===t);});
 var m=(t==='marche');
 document.getElementById('panel').style.display=m?'':'none';
 document.getElementById('filterbar').style.display=m?'':'none';
 document.getElementById('biasf').style.display=m?'':'none';
 document.getElementById('infos').style.display=(t==='infos')?'':'none';
 document.getElementById('g').style.display=(t==='infos')?'none':'';
 window.scrollTo(0,0);flt();}
function flt(){var v=(document.getElementById('q').value||'').toLowerCase();var shown=0;
 document.querySelectorAll('#g .card').forEach(function(c){
  var ok=true;
  if(tab==='surveillance')ok=FAV.indexOf(c.dataset.sym)>=0;
  else if(tab==='top')ok=(+c.dataset.rank)<15;
  else ok=(curCat==='Tous'||c.dataset.cat===curCat)&&(curBias==='Tous'||c.dataset.bias===curBias.toLowerCase())&&(!v||c.textContent.toLowerCase().includes(v));
  c.style.display=ok?'':'none';if(ok)shown++;});
 document.getElementById('emptyfav').style.display=(tab==='surveillance'&&shown===0)?'':'none';}
renderChips();markFavs();flt();
</script></body></html>"""


def _bias_key(bias):
    if "haussier" in bias:
        return "haussier"
    if "baissier" in bias:
        return "baissier"
    return "neutre"


def _fmt_num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    return f"{x:,.0f}".replace(",", " ") if abs(x) >= 1000 else f"{x:.4g}"


def build_market_panel(ok):
    bull = sum(1 for r in ok if "haussier" in r["bias"])
    bear = sum(1 for r in ok if "baissier" in r["bias"])
    neut = len(ok) - bull - bear
    rsis = [r["rsi"] for r in ok if r["rsi"]]
    avg_rsi = round(sum(rsis) / len(rsis)) if rsis else "n/a"
    # chips macro : indices d'abord, puis matières premières, devises, crypto
    prio = {"Indice": 0, "Matière première": 1, "Devise": 2, "Crypto": 3}
    macro = sorted([r for r in ok if r["category"] in prio],
                   key=lambda r: (prio[r["category"]], r["name"]))
    chips = []
    for r in macro[:12]:
        cls = "up" if "haussier" in r["bias"] else ("down" if "baissier" in r["bias"] else "")
        arrow = "▲" if cls == "up" else ("▼" if cls == "down" else "→")
        chips.append(f'<span class="chip"><b>{r["name"][:18]}</b> {_fmt_num(r["current"])} '
                     f'<span class="{cls}">{arrow}</span></span>')
    # leaders R/R
    leaders = [r for r in ok if (r.get("rr") or {}).get("rr_ratio")][:5]
    lead = " · ".join(f'{r["name"][:16]} (R/R {r["rr"]["rr_ratio"]})' for r in leaders)
    return (
        '<div class="panel"><h2>État du marché</h2>'
        '<div class="stats">'
        f'<div class="stat"><div class="v up">{bull}</div><div class="l">haussiers</div></div>'
        f'<div class="stat"><div class="v down">{bear}</div><div class="l">baissiers</div></div>'
        f'<div class="stat"><div class="v">{neut}</div><div class="l">neutres</div></div>'
        f'<div class="stat"><div class="v">{avg_rsi}</div><div class="l">RSI moyen</div></div>'
        '</div>'
        f'<div class="chips">{"".join(chips)}</div>'
        + (f'<div class="lead">🎯 <b>Meilleurs ratios R/R :</b> {lead}</div>' if lead else "")
        + '</div>'
    )


def build_index(results, out_dir, title="Analyse Tickers"):
    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]
    cards = []
    cats_order = ["Action PEA", "Action US", "Action", "ETF", "Crypto",
                  "Matière première", "Devise", "Indice"]
    present = [c for c in cats_order if any(r["category"] == c for r in ok)]
    present += [c for c in {r["category"] for r in ok} if c not in present]

    for idx, r in enumerate(ok):
        up = "haussier" in r["trend"]
        rsi = f"{r['rsi']:.0f}" if r["rsi"] else "n/a"
        stars = "★" * r["stars"] + "☆" * (5 - r["stars"])
        rr = r.get("rr") or {}
        rr_html = ""
        if rr.get("rr_ratio"):
            ratio = rr["rr_ratio"]
            cls = "rr-good" if ratio >= 1.8 else ("rr-mid" if ratio >= 1 else "rr-bad")
            rr_html = (f'<div class="rr {cls}">R/R {ratio} '
                       f'<small>+{rr["upside"]}% / −{rr["downside"]}%</small></div>')
        pat = f'<div class="pill">{", ".join(r["patterns"])}</div>' if r["patterns"] else ""
        news = f'<div class="news1">📰 {r["top_news"][:88]}</div>' if r.get("top_news") else ""
        bz = r.get("buy_zone")
        bz_html = (f'<div class="bz">🎯 zone achat {bz["low"]:.5g}–{bz["high"]:.5g} '
                   f'({bz["distance_pct"]}% sous)</div>' if bz else "")
        links = " · ".join(f'<a href="{fn}">{iv.upper()}</a>' for iv, fn in r["files"].items())
        sym = r["symbol"].replace("'", "")
        cards.append(
            f'<div class="card" data-cat="{r["category"]}" data-bias="{_bias_key(r["bias"])}" '
            f'data-sym="{sym}" data-rank="{idx}">'
            f'<button class="fav" onclick="toggleFav(\'{sym}\',this)">☆</button>'
            f'<div class="sym">{r.get("name", r["symbol"])}</div>'
            f'<div class="tag">{r["symbol"]} · {r["category"]}</div>'
            f'<div class="stars">{stars} <span class="biasl">{r["bias"]}</span></div>'
            f'{rr_html}'
            f'<div class="row {"up" if up else "down"}">{r["trend"]}</div>'
            f'<div class="row">RSI {rsi} ({r["rsi_state"]}) · cours {r["current"]}</div>'
            f'<div class="row">S {r["support"]} · R {r["resistance"]}</div>{bz_html}{pat}{news}'
            f'<div class="tflinks">📊 {links}</div></div>')
    for r in bad:
        cards.append(f'<div class="card err" data-cat="—" data-bias="neutre">'
                     f'<div class="sym">{r["symbol"]}</div>'
                     f'<div class="row">échec : {r.get("error")}</div></div>')

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    infos = (
        "<h3>À propos</h3>"
        f"<p>{len(ok)} actifs (actions US & PEA/UE, ETF, crypto, matières premières, "
        "devises, indices) — graphiques mis à jour automatiquement chaque jour, "
        "analyses rédigées à la demande.</p>"
        "<p><b>Note ⭐</b> = synthèse des signaux techniques (biais haussier↔baissier). "
        "<b>R/R</b> = ratio récompense (potentiel vers la résistance) ÷ risque (vers le bas "
        "de la zone d'achat). <b>Zone d'achat</b> = bande de confluence de supports.</p>"
        "<p><b>Onglets :</b> 📊 Marché (tout, filtrable par catégorie/biais) · "
        "⭐ Surveillance (tes favoris) · 🎯 Top R/R (15 meilleures configurations) · ℹ️ Infos.</p>"
        "<p style='color:var(--mut)'>⚠️ Outil d'analyse <b>factuelle</b> — pas un conseil en "
        "investissement ; ⭐, R/R et zones d'achat sont des synthèses de signaux, pas des "
        "ordres d'achat/vente. Sources : Yahoo Finance, exchanges crypto. "
        f"Généré le {date} UTC.</p>")
    html = (INDEX_TPL.replace("__CARDS__", "\n".join(cards))
            .replace("__PANEL__", build_market_panel(ok))
            .replace("__CATS__", json.dumps(present, ensure_ascii=False))
            .replace("__INFOS__", infos)
            .replace("__TITLE__", title)
            .replace("__N__", str(len(ok)))
            .replace("__DATE__", date))
    idx = os.path.join(out_dir, "index.html")
    with open(idx, "w", encoding="utf-8") as f:
        f.write(html)
    return idx


def main():
    ap = argparse.ArgumentParser(description="Analyse technique en lot d'une watchlist.")
    ap.add_argument("watchlist", nargs="?", help="Fichier export TradingView (.txt)")
    ap.add_argument("--symbols", help="Liste directe : 'EX:SYM,EX:SYM,...'")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--out", default=None, help="Dossier de sortie")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-news", action="store_true", help="Ne pas récupérer les actualités")
    ap.add_argument("--intervals", default="1d,1w", help="Unités de temps, ex. '1d,1w'")
    ap.add_argument("--sort", choices=["rr", "buyzone", "score", "watchlist"], default="rr",
                    help="Tri de l'index (rr = ratio risque/récompense)")
    ap.add_argument("--pwa", action="store_true", help="Générer une PWA installable (manifest/SW/icônes)")
    ap.add_argument("--title", default="Analyse Tickers", help="Nom de l'app PWA")
    ap.add_argument("--analysis-dir", default="analysis",
                    help="Dossier des analyses Markdown du skill (analysis/<clé>.md)")
    args = ap.parse_args()
    intervals = tuple(x.strip() for x in args.intervals.split(",") if x.strip())

    if args.symbols:
        parsed = parse_watchlist(args.symbols)
    elif args.watchlist:
        with open(args.watchlist, encoding="utf-8") as f:
            parsed = parse_watchlist(f.read())
    else:
        ap.error("fournir un fichier watchlist OU --symbols")

    if not parsed:
        print("Aucun symbole trouvé.", file=sys.stderr)
        sys.exit(1)
    symbols = [s for s, _ in parsed]
    cat_map = {s: c for s, c in parsed}

    out_dir = args.out or os.path.join(os.getcwd(), "ta_charts")
    os.makedirs(out_dir, exist_ok=True)
    print(f"{len(symbols)} tickers -> {out_dir}", file=sys.stderr)

    # Pré-résolution SÉQUENTIELLE des noms (Yahoo .info throttle sous concurrence) -> cache
    print("Résolution des noms…", file=sys.stderr)
    for s in symbols:
        try:
            a, _k, r = resolve(s)
            display_name(a, r)
        except Exception:
            pass

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        adir = args.analysis_dir if (args.analysis_dir and os.path.isdir(args.analysis_dir)) else None
        futs = {ex.submit(run_one, s, args.days, out_dir, not args.no_news, intervals,
                          adir, cat_map.get(s, "")): s
                for s in symbols}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            tag = "OK " if r["ok"] else "KO "
            print(f"  {tag}{r['symbol']}" + ("" if r["ok"] else f"  ({r.get('error')})"),
                  file=sys.stderr)

    order = {s.upper(): i for i, s in enumerate(symbols)}
    for r in results:
        if r["ok"]:
            r["rr"] = risk_reward(r)

    def sort_key(r):
        if not r["ok"]:
            return (2, 0)
        if args.sort == "watchlist":
            return (0, order.get(r["symbol"].upper(), 9999))
        if args.sort == "score":
            return (0, -r.get("score", 0))
        if args.sort == "buyzone":
            bz = r.get("buy_zone")
            return (0, abs(bz["distance_pct"]) if bz else 9999)
        return (0, -(r.get("rr") or {}).get("opp", -99))  # défaut: opportunité R/R desc

    results.sort(key=sort_key)

    # Injecte le sélecteur d'actifs (manifeste de navigation) dans chaque page
    ok = [r for r in results if r["ok"]]
    nav = [{"name": r["name"], "1d": r["files"].get("1d"), "1w": r["files"].get("1w")}
           for r in ok]
    nav_json = json.dumps(nav, ensure_ascii=False)
    for r in ok:
        for fnbase in r["files"].values():
            p = os.path.join(out_dir, fnbase)
            try:
                with open(p, encoding="utf-8") as f:
                    html = f.read()
                html = html.replace("const NAV = null; /*NAVSLOT*/",
                                    f"const NAV = {nav_json}; /*NAVSLOT*/", 1)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(html)
            except OSError:
                pass

    idx = build_index(results, out_dir, title=args.title)

    if args.pwa:
        html_files = [fn for r in ok for fn in r["files"].values()]
        ver = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        pwa.build_pwa(out_dir, args.title, html_files, ver)
        print("PWA générée (manifest + service worker + icônes + noindex)", file=sys.stderr)

    n_ok = sum(1 for r in results if r["ok"])
    print(f"\n{n_ok}/{len(symbols)} réussis. Index : {idx}", file=sys.stderr)
    print(idx)


if __name__ == "__main__":
    main()
