# -*- coding: utf-8 -*-
"""
pwa.py — Transforme un dossier de sortie en PWA installable (sans dépendance).

- Icônes PNG générées en pur stdlib (zlib+struct) : fond sombre + barres type chart.
- manifest.webmanifest, service worker (offline cache-first), robots.txt (noindex).
- Injecte dans chaque page : <link manifest>, theme-color, noindex, apple-touch-icon,
  et l'enregistrement du service worker.
"""
import json
import os
import struct
import zlib


# --------------------------------------------------------------------------- #
#  Icône PNG (pur stdlib)
# --------------------------------------------------------------------------- #
def _png_bytes(size, pixels):
    """pixels: bytearray RGB de longueur size*size*3 -> bytes PNG."""
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))
    raw = bytearray()
    stride = size * 3
    for y in range(size):
        raw.append(0)  # filtre 0
        raw.extend(pixels[y * stride:(y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def _make_icon(size):
    bg = (14, 15, 18)          # #0e0f12
    bars = [(0.18, 0.45, (55, 138, 221)),   # bleu
            (0.34, 0.30, (29, 158, 117)),   # teal
            (0.50, 0.62, (29, 158, 117)),   # teal haut
            (0.66, 0.40, (226, 75, 74)),    # coral
            (0.82, 0.55, (186, 117, 23))]   # ambre
    px = bytearray(bg[0:3] * (size * size))
    bw = int(size * 0.10)
    base = int(size * 0.82)
    for cx, h, col in bars:
        x0 = int(size * cx) - bw // 2
        top = base - int(size * h)
        for y in range(top, base):
            for x in range(x0, x0 + bw):
                if 0 <= x < size and 0 <= y < size:
                    i = (y * size + x) * 3
                    px[i:i + 3] = bytes(col)
    return _png_bytes(size, px)


# --------------------------------------------------------------------------- #
#  Manifest / SW / robots
# --------------------------------------------------------------------------- #
def _manifest(title, short):
    return json.dumps({
        "name": title, "short_name": short[:12],
        "start_url": "index.html", "scope": "./", "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#0e0f12", "theme_color": "#0e0f12",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }, ensure_ascii=False, indent=2)


def _sw(assets, ver):
    a = json.dumps(assets)
    return (
        "const CACHE='ta-" + ver + "';\n"
        "const ASSETS=" + a + ";\n"
        "self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE)"
        ".then(c=>c.addAll(ASSETS).catch(()=>{})).then(()=>self.skipWaiting()));});\n"
        "self.addEventListener('activate',e=>{e.waitUntil(caches.keys()"
        ".then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k))))"
        ".then(()=>self.clients.claim()));});\n"
        "self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;"
        "e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)"
        ".then(resp=>{const cp=resp.clone();caches.open(CACHE).then(c=>c.put(e.request,cp));return resp;})"
        ".catch(()=>caches.match('index.html'))));});\n"
    )


HEAD_TAGS = (
    '<link rel="manifest" href="manifest.webmanifest">'
    '<meta name="theme-color" content="#0e0f12">'
    '<meta name="robots" content="noindex,nofollow">'
    '<link rel="apple-touch-icon" href="icon-192.png">'
    '<meta name="apple-mobile-web-app-capable" content="yes">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    "<script>if('serviceWorker' in navigator){addEventListener('load',function(){"
    "navigator.serviceWorker.register('sw.js').catch(function(){});});}</script>"
)


def _inject_head(html):
    if "manifest.webmanifest" in html:
        return html  # déjà injecté
    if "</head>" in html:
        return html.replace("</head>", HEAD_TAGS + "</head>", 1)
    if "<body" in html:  # pas de <head> -> insère avant <body>
        return html.replace("<body", "<head>" + HEAD_TAGS + "</head><body", 1)
    return HEAD_TAGS + html


def build_pwa(out_dir, title, html_files, ver):
    """Écrit les assets PWA et injecte les tags dans chaque page HTML."""
    short = title.split()[0] if title else "Tickers"
    with open(os.path.join(out_dir, "icon-192.png"), "wb") as f:
        f.write(_make_icon(192))
    with open(os.path.join(out_dir, "icon-512.png"), "wb") as f:
        f.write(_make_icon(512))
    with open(os.path.join(out_dir, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        f.write(_manifest(title, short))
    with open(os.path.join(out_dir, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nDisallow: /\n")
    assets = ["index.html", "manifest.webmanifest", "icon-192.png", "icon-512.png"] + list(html_files)
    with open(os.path.join(out_dir, "sw.js"), "w", encoding="utf-8") as f:
        f.write(_sw(sorted(set(assets)), ver))
    # injecte les tags PWA dans index + toutes les pages
    for fn in set(["index.html"] + list(html_files)):
        p = os.path.join(out_dir, fn)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            html = f.read()
        html2 = _inject_head(html)
        if html2 != html:
            with open(p, "w", encoding="utf-8") as f:
                f.write(html2)
