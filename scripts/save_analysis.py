# -*- coding: utf-8 -*-
"""
save_analysis.py — Enregistre une analyse (sortie du skill) dans l'app dashboard.

La page de chaque actif affiche `analysis/<clé>.md` si présent. Ce script écrit
le Markdown au bon endroit, avec la bonne clé (= symbole TradingView normalisé).

Clé : "EURONEXT:MC" -> "EURONEXT_MC". Utiliser le MÊME symbole que dans watchlist.txt.

Usage (depuis n'importe quelle session Claude Code, après avoir produit le rapport) :
  python save_analysis.py --symbol "EURONEXT:MC" --file rapport_lvmh.md
  python save_analysis.py --symbol "EURONEXT:MC" --text "## LVMH..."
Dossier cible par défaut : le repo de l'app (Desktop\\Analyse-Tickers-App\\analysis).
Après écriture, committer/pusher le repo (ou attendre le rebuild) pour publier.
"""
import argparse
import os
import re
import sys

DEFAULT_DIR = r"C:\Users\rabau\Desktop\Analyse-Tickers-App\analysis"


def key(symbol):
    return re.sub(r"[^A-Za-z0-9]+", "_", symbol.strip().upper()).strip("_")


def main():
    ap = argparse.ArgumentParser(description="Enregistre une analyse du skill dans l'app.")
    ap.add_argument("--symbol", required=True, help="Symbole TradingView, ex. EURONEXT:MC")
    ap.add_argument("--file", help="Fichier Markdown source")
    ap.add_argument("--text", help="Contenu Markdown direct")
    ap.add_argument("--dir", default=DEFAULT_DIR, help="Dossier analysis/ de l'app")
    args = ap.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            md = f.read()
    elif args.text:
        md = args.text
    else:
        md = sys.stdin.read()
    if not md.strip():
        print("ERREUR : contenu vide.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.dir, exist_ok=True)
    out = os.path.join(args.dir, key(args.symbol) + ".md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    print(out)


if __name__ == "__main__":
    main()
