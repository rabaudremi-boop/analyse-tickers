# -*- coding: utf-8 -*-
"""
fetch_news.py — Actualités récentes par ticker (gratuit, sans clé).

- Actions/indices/forex : Yahoo Finance (yfinance .news) en priorité, repli Google News.
- Crypto : Google News RSS (requête "<base> crypto").

Aucune dépendance en plus (urllib + xml stdlib ; yfinance déjà présent).
"""
import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ticker-analysis"}


def _google_news(query, n=4, lang="fr"):
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote(query)
           + f"&hl={lang}&gl=FR&ceid=FR:{lang}")
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    root = ET.fromstring(raw)
    out = []
    for it in root.iter("item"):
        title = it.findtext("title") or ""
        link = it.findtext("link") or ""
        pub = it.findtext("pubDate") or ""
        src_el = it.find("source")
        source = src_el.text if src_el is not None else ""
        out.append({"title": html.unescape(title).strip(), "link": link,
                    "date": pub[:16], "source": source or "Google News"})
        if len(out) >= n:
            break
    return out


def _yf_news(symbol, n=4):
    import yfinance as yf
    raw = yf.Ticker(symbol).news or []
    out = []
    for it in raw[:n + 2]:
        c = it.get("content", it) if isinstance(it, dict) else {}
        title = c.get("title") or it.get("title")
        link = ((c.get("canonicalUrl") or {}).get("url")
                or (c.get("clickThroughUrl") or {}).get("url")
                or it.get("link"))
        prov = (c.get("provider") or {}).get("displayName") or it.get("publisher") or ""
        pub = c.get("pubDate") or it.get("providerPublishTime") or ""
        if title:
            out.append({"title": str(title).strip(), "link": link,
                        "date": str(pub)[:16], "source": prov})
        if len(out) >= n:
            break
    return out


def crypto_base(symbol):
    return re.sub(r"(USDT|USDC|BUSD|USD|PERP)$", "", symbol.upper()) or symbol


def get_news(asset_class, symbol, n=4):
    """asset_class: crypto|stock|index|forex ; symbol: symbole résolu (ex. AAPL, HYPEUSDT)."""
    try:
        if asset_class == "crypto":
            return _google_news(crypto_base(symbol) + " crypto", n)
        # actions / indices / forex
        try:
            yfn = _yf_news(symbol, n)
            if yfn:
                return yfn
        except Exception:
            pass
        q = symbol.replace("=X", "").replace("^", "")
        suffix = " stock" if asset_class == "stock" else ""
        return _google_news(q + suffix, n)
    except Exception:
        return []


if __name__ == "__main__":
    import sys, json
    ac = sys.argv[1] if len(sys.argv) > 1 else "crypto"
    sym = sys.argv[2] if len(sys.argv) > 2 else "BTCUSDT"
    print(json.dumps(get_news(ac, sym), ensure_ascii=False, indent=1))
