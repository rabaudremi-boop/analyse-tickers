# -*- coding: utf-8 -*-
"""
fetch_ohlcv.py — Résolveur de symboles TradingView -> bougies OHLCV (gratuit).

Entrée : un symbole au format TradingView `EXCHANGE:SYMBOL` (ou symbole nu).
  - Crypto  -> klines Binance (spot puis futures) avec repli Bybit.
  - Actions -> Yahoo Finance (yfinance), avec mapping de suffixe par place.
  - Forex   -> Yahoo (`EURUSD=X`).
  - Indices -> mapping des plus courants vers les symboles Yahoo (^GSPC, ...).

Sortie : (candles, meta)
  candles = [{"time":"YYYY-MM-DD","open":..,"high":..,"low":..,"close":..,"volume":..}, ...]
  meta    = {"input","asset_class","source","resolved","error"}
"""
import re

import requests

CRYPTO_EXCHANGES = {
    "BINANCE", "BYBIT", "OKX", "COINBASE", "KUCOIN", "KRAKEN", "BITGET",
    "GATEIO", "GATE", "MEXC", "HUOBI", "HTX", "BITSTAMP", "BINANCEUS",
    "HYPERLIQUID", "CRYPTO", "BITFINEX", "PHEMEX",
}
FOREX_EXCHANGES = {"FX", "OANDA", "FX_IDC", "FOREXCOM", "FXCM", "SAXO", "ICMARKETS"}
# Place boursière -> suffixe yfinance
STOCK_SUFFIX = {
    "EURONEXT": ".PA", "EURONEXTPAR": ".PA", "EPA": ".PA",
    "LSE": ".L", "LSIN": ".L",
    "XETR": ".DE", "FWB": ".DE", "TRADEGATE": ".DE", "GETTEX": ".DE",
    "SIX": ".SW", "BME": ".MC", "BIT": ".MI", "MIL": ".MI",
    "TSX": ".TO", "TSXV": ".V", "ASX": ".AX", "HKEX": ".HK",
    "EURONEXTAMS": ".AS", "EURONEXTBRU": ".BR", "EURONEXTLIS": ".LS",
    "OMXSTO": ".ST", "OMXHEX": ".HE", "OMXCOP": ".CO", "OSL": ".OL",
}
US_STOCK_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "NYSEARCA", "BATS", "OTC", "CBOE", "ARCA"}
INDEX_MAP = {
    "SPX": "^GSPC", "SP500": "^GSPC", "US500": "^GSPC", "ES": "^GSPC",
    "NDX": "^NDX", "US100": "^NDX", "IXIC": "^IXIC", "NASDAQ": "^IXIC",
    "DJI": "^DJI", "US30": "^DJI", "DJ": "^DJI",
    "VIX": "^VIX", "RUT": "^RUT", "US2000": "^RUT",
    "DAX": "^GDAXI", "DE40": "^GDAXI", "CAC": "^FCHI", "CAC40": "^FCHI", "FR40": "^FCHI",
    "UKX": "^FTSE", "UK100": "^FTSE", "FTSE": "^FTSE",
    "NI225": "^N225", "JP225": "^N225", "HSI": "^HSI",
}
HEADERS = {"User-Agent": "ticker-analysis/2.0", "Accept": "application/json"}
TIMEOUT = 30


def _bn_iso(ms):
    import datetime as dt
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def _norm_crypto_symbol(sym):
    sym = sym.upper().replace("-", "").replace("/", "").replace("PERP", "")
    if sym.endswith("USD") and not sym.endswith(("USDT", "USDC", "BUSD")):
        sym = sym[:-3] + "USDT"
    return sym


def _crypto_klines(sym, days, interval="1d"):
    sym = _norm_crypto_symbol(sym)
    limit = min(max(days, 30), 1000)
    bn_int = "1w" if interval == "1w" else "1d"
    by_int = "W" if interval == "1w" else "D"
    # 1) Binance spot
    for base in ("https://api.binance.com/api/v3/klines",
                 "https://fapi.binance.com/fapi/v1/klines"):
        try:
            r = requests.get(base, params={"symbol": sym, "interval": bn_int, "limit": limit},
                             headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200 and isinstance(r.json(), list) and r.json():
                kl = r.json()
                return [{"time": _bn_iso(k[0]), "open": float(k[1]), "high": float(k[2]),
                         "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])}
                        for k in kl], f"binance:{sym}"
        except (requests.RequestException, ValueError):
            pass
    # 2) Bybit (newest first -> reverse)
    try:
        r = requests.get("https://api.bybit.com/v5/market/kline",
                         params={"category": "linear", "symbol": sym, "interval": by_int, "limit": limit},
                         headers=HEADERS, timeout=TIMEOUT)
        j = r.json()
        rows = (j.get("result") or {}).get("list") or []
        if rows:
            rows = list(reversed(rows))
            return [{"time": _bn_iso(int(x[0])), "open": float(x[1]), "high": float(x[2]),
                     "low": float(x[3]), "close": float(x[4]), "volume": float(x[5])}
                    for x in rows], f"bybit:{sym}"
    except (requests.RequestException, ValueError, KeyError):
        pass
    return None, None


def _yf_history(yf_symbol, days, interval="1d"):
    import yfinance as yf
    if interval == "1w":
        yf_int, period = "1wk", "5y"
    else:
        yf_int = "1d"
        period = "2y" if days > 365 else ("1y" if days > 180 else "6mo")
    tk = yf.Ticker(yf_symbol)
    hist = tk.history(period=period, interval=yf_int)
    if hist is None or hist.empty:
        return None
    out = []
    for ts, row in hist.iterrows():
        out.append({"time": ts.strftime("%Y-%m-%d"),
                    "open": float(row["Open"]), "high": float(row["High"]),
                    "low": float(row["Low"]), "close": float(row["Close"]),
                    "volume": float(row.get("Volume", 0) or 0)})
    return out[-days:] if days else out


def resolve(tv_symbol):
    """Renvoie (asset_class, fetch_kind, resolved_symbol)."""
    s = tv_symbol.strip().upper()
    exch, sym = (s.split(":", 1) if ":" in s else ("", s))
    exch = exch.strip()
    sym = sym.strip()
    if exch in CRYPTO_EXCHANGES or (not exch and sym.endswith(("USDT", "USDC"))):
        return "crypto", "crypto", sym
    if exch in FOREX_EXCHANGES or (len(sym) == 6 and sym.isalpha() and exch in {"", "FX"}):
        return "forex", "yfinance", f"{sym}=X"
    if sym in INDEX_MAP:
        return "index", "yfinance", INDEX_MAP[sym]
    if exch in STOCK_SUFFIX:
        return "stock", "yfinance", f"{sym}{STOCK_SUFFIX[exch]}"
    # US ou inconnu -> tenter yfinance brut
    return "stock", "yfinance", sym


_NAME_CACHE = {}


def display_name(asset_class, resolved):
    """Nom lisible de l'actif (pour fichiers/titres). Crypto -> base ; sinon Yahoo shortName.
    Mis en cache (évite les appels .info en double, ex. 1D + 1W du même ticker)."""
    if asset_class == "crypto":
        return re.sub(r"(USDT|USDC|BUSD|USD|PERP)$", "", resolved.upper()) or resolved
    if resolved in _NAME_CACHE:
        return _NAME_CACHE[resolved]
    name = resolved
    try:
        # API search Yahoo : fiable et sans throttle (contrairement à yfinance .info)
        r = requests.get("https://query2.finance.yahoo.com/v1/finance/search",
                         params={"q": resolved, "quotesCount": 1, "newsCount": 0},
                         headers=HEADERS, timeout=15)
        q = (r.json().get("quotes") or [{}])[0]
        nm = q.get("shortname") or q.get("longname") or ""
        nm = re.split(r"\s{2,}", nm.strip())[0]      # vire le padding Yahoo ("SAP SE      I")
        nm = re.sub(r"\s+", " ", nm).strip()
        if nm:
            name = nm
    except Exception:
        pass
    _NAME_CACHE[resolved] = name
    return name


def fetch_ohlcv(tv_symbol, days=365, interval="1d"):
    asset, kind, resolved = resolve(tv_symbol)
    meta = {"input": tv_symbol, "asset_class": asset, "source": kind,
            "resolved": resolved, "interval": interval, "error": None}
    try:
        if kind == "crypto":
            candles, src = _crypto_klines(resolved, days, interval)
            if candles:
                meta["source"] = src
                return candles, meta
            meta["error"] = "klines crypto introuvables (symbole non listé ?)"
            return None, meta
        else:
            candles = _yf_history(resolved, days, interval)
            if candles:
                meta["source"] = f"yfinance:{resolved}"
                return candles, meta
            meta["error"] = "yfinance : aucune donnée (symbole/place à vérifier)"
            return None, meta
    except Exception as e:
        meta["error"] = f"{type(e).__name__}: {e}"
        return None, meta


if __name__ == "__main__":
    import sys, json
    for arg in sys.argv[1:]:
        c, m = fetch_ohlcv(arg)
        print(json.dumps({"meta": m, "n": len(c) if c else 0,
                          "last": c[-1] if c else None}, ensure_ascii=False))
