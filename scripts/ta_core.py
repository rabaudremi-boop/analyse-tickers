# -*- coding: utf-8 -*-
"""
ta_core.py — Indicateurs d'analyse technique (pur Python, sans dépendance lourde).

Toutes les fonctions prennent des listes de float et renvoient des structures
JSON-sérialisables. Les séries alignées sur l'index des bougies utilisent `None`
pendant la période de chauffe (le rendu les ignore).
"""
from statistics import pstdev


def ema(vals, p):
    if not vals:
        return []
    k = 2.0 / (p + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def sma_series(vals, p):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= p:
            s -= vals[i - p]
        if i >= p - 1:
            out[i] = s / p
    return out


def bollinger(vals, p=20, k=2.0):
    mid = sma_series(vals, p)
    up = [None] * len(vals)
    lo = [None] * len(vals)
    for i in range(len(vals)):
        if i >= p - 1:
            window = vals[i - p + 1:i + 1]
            sd = pstdev(window)
            up[i] = mid[i] + k * sd
            lo[i] = mid[i] - k * sd
    return mid, up, lo


def rsi(vals, p=14):
    out = [None] * len(vals)
    if len(vals) <= p:
        return out
    gain = loss = 0.0
    for i in range(1, p + 1):
        d = vals[i] - vals[i - 1]
        gain += max(d, 0)
        loss += max(-d, 0)
    ag, al = gain / p, loss / p
    out[p] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(p + 1, len(vals)):
        d = vals[i] - vals[i - 1]
        ag = (ag * (p - 1) + max(d, 0)) / p
        al = (al * (p - 1) + max(-d, 0)) / p
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def macd(vals, fast=12, slow=26, signal=9):
    ef, es = ema(vals, fast), ema(vals, slow)
    line = [ef[i] - es[i] for i in range(len(vals))]
    sig = ema(line, signal)
    hist = [line[i] - sig[i] for i in range(len(vals))]
    return line, sig, hist


def atr(highs, lows, closes, p=14):
    n = len(closes)
    out = [None] * n
    if n < 2:
        return out
    trs = [highs[0] - lows[0]]
    for i in range(1, n):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    if n <= p:
        return out
    a = sum(trs[1:p + 1]) / p
    out[p] = a
    for i in range(p + 1, n):
        a = (a * (p - 1) + trs[i]) / p
        out[i] = a
    return out


def swing_points(highs, lows, k=5):
    """Renvoie (swing_highs, swing_lows) = listes de (index, prix)."""
    sh, sl = [], []
    for i in range(k, len(highs) - k):
        if highs[i] == max(highs[i - k:i + k + 1]):
            sh.append((i, highs[i]))
        if lows[i] == min(lows[i - k:i + k + 1]):
            sl.append((i, lows[i]))
    return sh, sl


def sr_zones(highs, lows, current, k=5, tol=0.018, max_each=5):
    """Zones de support/résistance par clustering des pivots (pondérées par touches)."""
    sh, sl = swing_points(highs, lows, k)
    levels = sorted(p for _, p in sh + sl)
    zones = []
    for p in levels:
        if zones and abs(p - zones[-1]["c"]) / zones[-1]["c"] <= tol:
            z = zones[-1]
            z["pts"].append(p)
            z["c"] = sum(z["pts"]) / len(z["pts"])
        else:
            zones.append({"c": p, "pts": [p]})
    out = [{"price": round(z["c"], 6), "touches": len(z["pts"])} for z in zones]
    res = sorted([z for z in out if z["price"] > current], key=lambda z: z["price"])[:max_each]
    sup = sorted([z for z in out if z["price"] < current], key=lambda z: -z["price"])[:max_each]
    return sup, res


def fib_levels(highs, lows):
    hi, lo = max(highs), min(lows)
    rng = hi - lo
    return {f"{r*100:.1f}%": round(hi - rng * r, 6)
            for r in (0.236, 0.382, 0.5, 0.618, 0.786)}, round(hi, 6), round(lo, 6)


def daily_pivots(prev_high, prev_low, prev_close):
    pp = (prev_high + prev_low + prev_close) / 3
    rng = prev_high - prev_low
    return {
        "PP": round(pp, 6),
        "R1": round(2 * pp - prev_low, 6), "S1": round(2 * pp - prev_high, 6),
        "R2": round(pp + rng, 6), "S2": round(pp - rng, 6),
        "R3": round(pp + 2 * rng, 6), "S3": round(pp - 2 * rng, 6),
    }


def regression_channel(closes, window=120, k=2.0):
    n = min(window, len(closes))
    if n < 5:
        return None
    y = closes[-n:]
    x = list(range(n))
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    slope = sxy / sxx if sxx else 0.0
    inter = my - slope * mx
    fit = [inter + slope * i for i in range(n)]
    sd = pstdev([y[i] - fit[i] for i in range(n)]) if n > 1 else 0.0
    return {
        "start": len(closes) - n,
        "mid": [round(v, 6) for v in fit],
        "upper": [round(v + k * sd, 6) for v in fit],
        "lower": [round(v - k * sd, 6) for v in fit],
        "slope_pct_per_bar": round(slope / my * 100, 4) if my else None,
    }


def volume_profile(highs, lows, closes, vols, bins=60, value_area=0.7):
    lo, hi = min(lows), max(highs)
    if hi <= lo:
        return None
    width = (hi - lo) / bins
    buckets = [0.0] * bins
    for i in range(len(closes)):
        tp = (highs[i] + lows[i] + closes[i]) / 3
        if tp != tp or width <= 0:  # NaN-safe
            continue
        b = min(bins - 1, max(0, int((tp - lo) / width)))
        vv = vols[i] if vols else 0
        buckets[b] += vv if vv == vv else 0  # ignore NaN
    if sum(buckets) == 0:
        return None
    poc_b = max(range(bins), key=lambda b: buckets[b])
    total = sum(buckets)
    target = total * value_area
    lo_b = hi_b = poc_b
    acc = buckets[poc_b]
    while acc < target and (lo_b > 0 or hi_b < bins - 1):
        down = buckets[lo_b - 1] if lo_b > 0 else -1
        up = buckets[hi_b + 1] if hi_b < bins - 1 else -1
        if up >= down and hi_b < bins - 1:
            hi_b += 1
            acc += buckets[hi_b]
        elif lo_b > 0:
            lo_b -= 1
            acc += buckets[lo_b]
        else:
            break
    return {
        "poc": round(lo + (poc_b + 0.5) * width, 6),
        "vah": round(lo + (hi_b + 1) * width, 6),
        "val": round(lo + lo_b * width, 6),
    }


def ideal_buy_zone(cur, sup, fib, e50_last, e200_last, pivots, vprofile, atr_last):
    """Zone d'achat potentielle = bande de prix SOUS le cours où le plus de supports
    convergent (confluence). Aide technique, PAS un signal d'achat.
    Renvoie {low, high, mid, weight, distance_pct, components[]} ou None."""
    cands = []  # (prix, poids, libellé)
    for z in (sup or []):
        cands.append((z["price"], 1 + 0.4 * z.get("touches", 1), f"support ({z.get('touches',1)}x)"))
    for k, v in (fib or {}).items():
        if v < cur:
            w = 2.0 if k in ("61.8%", "50.0%") else (1.5 if k == "78.6%" else 1.0)
            cands.append((v, w, f"fib {k}"))
    if e200_last and e200_last < cur:
        cands.append((e200_last, 2.0, "EMA200"))
    if e50_last and e50_last < cur:
        cands.append((e50_last, 1.5, "EMA50"))
    for k in ("S1", "S2", "S3"):
        v = (pivots or {}).get(k)
        if v and v < cur:
            cands.append((v, 1.0, f"pivot {k}"))
    if vprofile:
        if vprofile.get("poc") and vprofile["poc"] < cur:
            cands.append((vprofile["poc"], 2.0, "POC volume"))
        if vprofile.get("val") and vprofile["val"] < cur:
            cands.append((vprofile["val"], 1.5, "VAL volume"))

    # garder les niveaux pas trop loin sous le prix (<=40 %)
    cands = [c for c in cands if cur * 0.6 <= c[0] < cur]
    if not cands:
        return None
    cands.sort(key=lambda c: c[0])
    # Largeur de zone BORNÉE (~3,5 %) : on regroupe par rapport au BAS du cluster
    # pour éviter l'effet de chaîne qui élargirait la zone à tout ce qui est sous le prix.
    zone_w = 0.035

    clusters = []
    for p, w, lbl in cands:
        if clusters and (p - clusters[-1]["lo"]) / clusters[-1]["lo"] <= zone_w:
            c = clusters[-1]
            c["hi"] = p
            c["w"] += w
            c["prices"].append(p)
            c["items"].append(lbl)
        else:
            clusters.append({"lo": p, "hi": p, "w": w, "prices": [p], "items": [lbl]})
    # meilleur = confluence la plus forte ; à poids ~égal, préférer la plus proche du prix
    best = max(clusters, key=lambda c: (round(c["w"], 1), c["hi"]))
    lo, hi = min(best["prices"]), max(best["prices"])
    if (hi - lo) / hi < 0.004 and atr_last:  # zone quasi ponctuelle -> élargir de ±0.4 ATR
        lo, hi = lo - 0.4 * atr_last, hi + 0.4 * atr_last
    return {
        "low": round(lo, 6), "high": round(hi, 6), "mid": round((lo + hi) / 2, 6),
        "weight": round(best["w"], 1),
        "distance_pct": round((cur - hi) / cur * 100, 2),
        "components": best["items"],
    }


def technical_score(closes, e20, e50, e200, rsi_last, macd_line_last,
                    macd_hist_last, bb_mid_last, sup, res, patterns, vprofile):
    """Score de biais TECHNIQUE composite -> note ⭐ (synthèse de signaux, PAS un conseil).
    Renvoie {score, stars(1-5), bias, drivers[]} ; 5★=haussier fort, 1★=baissier fort."""
    cur = closes[-1]
    score = 0.0
    drivers = []

    def add(pts, msg):
        nonlocal score
        score += pts
        drivers.append(f"{pts:+.1f} {msg}")

    if e200:
        add(2 if cur > e200[-1] else -2, "prix vs EMA200")
    if e20 and e50 and e200:
        if e20[-1] > e50[-1] > e200[-1]:
            add(2, "EMA empilées haussières")
        elif e20[-1] < e50[-1] < e200[-1]:
            add(-2, "EMA empilées baissières")
    if e50:
        add(1 if cur > e50[-1] else -1, "prix vs EMA50")
    if rsi_last is not None:
        add(round(max(-2, min(2, (rsi_last - 50) / 10)), 1), f"RSI {rsi_last:.0f}")
    if macd_hist_last is not None:
        add(1 if macd_hist_last >= 0 else -1, "MACD histogramme")
    if macd_line_last is not None:
        add(0.5 if macd_line_last >= 0 else -0.5, "MACD ligne")
    if bb_mid_last is not None:
        add(0.5 if cur > bb_mid_last else -0.5, "prix vs moyenne Bollinger")
    if sup and res:
        ds = (cur - sup[0]["price"]) / cur
        dr = (res[0]["price"] - cur) / cur
        if dr > ds * 1.5:
            add(1, "marge vers la résistance")
        elif ds > dr * 1.5:
            add(-0.5, "proche résistance")
    for p in patterns:
        if "bottom" in p["type"]:
            add(2, "figure double bottom")
        elif "top" in p["type"]:
            add(-2, "figure double top")
    if vprofile and vprofile.get("poc"):
        add(0.5 if cur > vprofile["poc"] else -0.5, "prix vs POC volume")

    if score >= 5:
        stars, bias = 5, "biais haussier fort"
    elif score >= 1.5:
        stars, bias = 4, "biais haussier modéré"
    elif score > -1.5:
        stars, bias = 3, "neutre / indécis"
    elif score > -5:
        stars, bias = 2, "biais baissier modéré"
    else:
        stars, bias = 1, "biais baissier fort"
    return {"score": round(score, 1), "stars": stars, "bias": bias,
            "drivers": sorted(drivers, key=lambda d: -abs(float(d.split()[0])))[:6]}


def detect_patterns(highs, lows, closes, k=5, tol=0.02):
    """Détection heuristique simple de figures récentes."""
    sh, sl = swing_points(highs, lows, k)
    out = []
    # Double top : 2 derniers swing highs proches
    if len(sh) >= 2:
        (i1, p1), (i2, p2) = sh[-2], sh[-1]
        if abs(p1 - p2) / max(p1, p2) <= tol and closes[-1] < min(p1, p2):
            out.append({"type": "double top (baissier)", "index": i2, "price": round(p2, 6)})
    # Double bottom
    if len(sl) >= 2:
        (i1, p1), (i2, p2) = sl[-2], sl[-1]
        if abs(p1 - p2) / max(p1, p2) <= tol and closes[-1] > max(p1, p2):
            out.append({"type": "double bottom (haussier)", "index": i2, "price": round(p2, 6)})
    # Triangle : highs descendants + lows montants sur les 4 derniers pivots
    if len(sh) >= 2 and len(sl) >= 2:
        hh = sh[-1][1] < sh[-2][1]
        ll = sl[-1][1] > sl[-2][1]
        if hh and ll:
            out.append({"type": "triangle symétrique (compression)", "index": len(closes) - 1,
                        "price": round(closes[-1], 6)})
    return out
