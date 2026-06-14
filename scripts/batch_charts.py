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
    """Extrait les symboles d'un export TradingView (gère ###Sections et virgules)."""
    tokens = re.split(r"[,\n\r]+", text)
    out = []
    for tok in tokens:
        tok = tok.strip()
        if not tok or tok.startswith("###"):
            continue
        out.append(tok)
    # dédoublonne en gardant l'ordre
    seen, uniq = set(), []
    for s in out:
        if s.upper() not in seen:
            seen.add(s.upper())
            uniq.append(s)
    return uniq


def safe_name(sym):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", sym)


def run_one(sym, days, out_dir, with_news=True, intervals=("1d", "1w"), analysis_dir=None):
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
            nice = safe_name(data.get("name", sym))[:40].strip("_") or safe_name(sym)
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
    return {"symbol": sym, "ok": True, "files": files, "name": data.get("name", sym),
            "asset": meta["asset_class"], "trend": r["trend"], "rsi": r["rsi"],
            "rsi_state": r["rsi_state"], "support": r["near_support"],
            "resistance": r["near_resistance"], "patterns": r["patterns"],
            "current": r["current"], "stars": r["stars"], "bias": r["bias"],
            "score": r["score"],
            "top_news": data["news"][0]["title"] if data.get("news") else "",
            "buy_zone": data.get("buy_zone")}


INDEX_TPL = r"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Mes favoris — analyse technique</title>
<style>
:root{color-scheme:light dark}
body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#fff;color:#1a1a1a}
@media(prefers-color-scheme:dark){body{background:#0e0f12;color:#d8d8d8}.card{background:#16181d!important;border-color:#262a31!important}}
.wrap{max-width:1100px;margin:0 auto;padding:20px}
h1{font-size:20px;margin:0 0 2px}.sub{font-size:12px;opacity:.6;margin-bottom:14px}
input{width:100%;max-width:340px;padding:9px 12px;border:1px solid #ccc;border-radius:8px;margin-bottom:16px;font-size:14px;background:transparent;color:inherit}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.card{color:inherit;background:#fafafa;border:1px solid #e6e6e6;border-radius:10px;padding:12px 14px}
.card:hover{border-color:#999}
.tflinks{margin-top:9px;font-size:12px}
.tflinks a{color:#378ADD;text-decoration:none;font-weight:500;border:1px solid #378ADD55;border-radius:6px;padding:2px 9px;margin-right:5px}
.tflinks a:hover{background:#378ADD22}
.sym{font-size:15px;font-weight:600}.tag{font-size:10px;opacity:.6;text-transform:uppercase}
.row{font-size:12px;margin-top:6px;opacity:.85}
.up{color:#1D9E75}.down{color:#E24B4A}
.stars{font-size:14px;color:#BA7517;letter-spacing:1px;margin-top:6px}
.biasl{font-size:11px;color:inherit;opacity:.7;letter-spacing:0}
.bz{font-size:11px;margin-top:6px;color:#0F6E56;background:rgba(29,158,117,.12);border-radius:6px;padding:3px 7px;display:inline-block}
@media(prefers-color-scheme:dark){.bz{color:#5DCAA5}}
.news1{font-size:11px;opacity:.6;margin-top:7px;line-height:1.4}
.pill{display:inline-block;font-size:10px;padding:1px 7px;border-radius:10px;background:#7F77DD22;color:#7F77DD;margin-top:6px}
.err{opacity:.5;border-style:dashed}
.disc{font-size:11px;opacity:.5;margin-top:18px}
</style></head><body><div class="wrap">
<h1>Mes favoris — analyse technique</h1>
<div class="sub">__N__ tickers · généré __DATE__ UTC · clique un ticker pour le graphique interactif complet</div>
<input id="q" placeholder="filtrer (ticker, tendance…)" oninput="flt()">
<div class="grid" id="g">__CARDS__</div>
<div class="disc">Aide à l'analyse graphique — pas un conseil d'investissement. Niveaux calculés automatiquement.</div>
</div><script>
function flt(){var v=document.getElementById('q').value.toLowerCase();
document.querySelectorAll('#g .card').forEach(function(c){c.style.display=c.textContent.toLowerCase().includes(v)?'':'none';});}
</script></body></html>"""


def build_index(results, out_dir):
    cards = []
    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]
    for r in ok:
        up = "haussier" in r["trend"]
        rsi = f"{r['rsi']:.0f}" if r["rsi"] else "n/a"
        pat = f'<div class="pill">{", ".join(r["patterns"])}</div>' if r["patterns"] else ""
        stars = "★" * r["stars"] + "☆" * (5 - r["stars"])
        news = (f'<div class="news1">📰 {r["top_news"][:90]}</div>'
                if r.get("top_news") else "")
        bz = r.get("buy_zone")
        bz_html = (f'<div class="bz">🎯 zone achat {bz["low"]:.5g}–{bz["high"]:.5g} '
                   f'({bz["distance_pct"]}% sous)</div>' if bz else "")
        links = " · ".join(f'<a href="{fn}">{iv.upper()}</a>' for iv, fn in r["files"].items())
        cards.append(
            f'<div class="card">'
            f'<div class="sym">{r.get("name", r["symbol"])}</div>'
            f'<div class="tag">{r["symbol"]} · {r["asset"]}</div>'
            f'<div class="stars">{stars} <span class="biasl">{r["bias"]}</span></div>'
            f'<div class="row {"up" if up else "down"}">{r["trend"]}</div>'
            f'<div class="row">RSI {rsi} ({r["rsi_state"]}) · cours {r["current"]}</div>'
            f'<div class="row">S {r["support"]} · R {r["resistance"]}</div>{bz_html}{pat}{news}'
            f'<div class="tflinks">📊 {links}</div></div>')
    for r in bad:
        cards.append(f'<div class="card err"><div class="sym">{r["symbol"]}</div>'
                     f'<div class="row">échec : {r.get("error")}</div></div>')
    html = (INDEX_TPL.replace("__CARDS__", "\n".join(cards))
            .replace("__N__", str(len(ok)))
            .replace("__DATE__", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")))
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
    ap.add_argument("--sort", choices=["buyzone", "score", "watchlist"], default="buyzone",
                    help="Tri de l'index")
    ap.add_argument("--pwa", action="store_true", help="Générer une PWA installable (manifest/SW/icônes)")
    ap.add_argument("--title", default="Analyse Tickers", help="Nom de l'app PWA")
    ap.add_argument("--analysis-dir", default="analysis",
                    help="Dossier des analyses Markdown du skill (analysis/<clé>.md)")
    args = ap.parse_args()
    intervals = tuple(x.strip() for x in args.intervals.split(",") if x.strip())

    if args.symbols:
        symbols = parse_watchlist(args.symbols)
    elif args.watchlist:
        with open(args.watchlist, encoding="utf-8") as f:
            symbols = parse_watchlist(f.read())
    else:
        ap.error("fournir un fichier watchlist OU --symbols")

    if not symbols:
        print("Aucun symbole trouvé.", file=sys.stderr)
        sys.exit(1)

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
        futs = {ex.submit(run_one, s, args.days, out_dir, not args.no_news, intervals, adir): s
                for s in symbols}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            tag = "OK " if r["ok"] else "KO "
            print(f"  {tag}{r['symbol']}" + ("" if r["ok"] else f"  ({r.get('error')})"),
                  file=sys.stderr)

    order = {s.upper(): i for i, s in enumerate(symbols)}

    def sort_key(r):
        if not r["ok"]:
            return (2, 0)
        if args.sort == "watchlist":
            return (0, order.get(r["symbol"].upper(), 9999))
        if args.sort == "score":
            return (0, -r.get("score", 0))
        bz = r.get("buy_zone")  # proximité à la zone d'achat (|distance|)
        return (0, abs(bz["distance_pct"]) if bz else 9999)

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

    idx = build_index(results, out_dir)

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
