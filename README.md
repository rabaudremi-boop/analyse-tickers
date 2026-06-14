# Analyse Tickers — dashboard PWA

Application web (PWA installable) d'analyse technique de mes tickers, générée
automatiquement et déployée sur GitHub Pages.

- **Données** : prix/OHLCV via Yahoo Finance (actions/ETF/indices) et exchanges
  crypto (Binance/Bybit) — gratuit, sans clé.
- **Analyse** : EMA, Bollinger, S/R, Fibonacci, pivots, volume profile (POC/VA),
  RSI, MACD, figures, note ⭐ de biais, **zone d'achat potentielle**, actualités.
- **Sortie** : un graphique interactif par ticker (1D + 1W) + un index trié par
  proximité à la zone d'achat, avec sélecteur d'actif intégré.

⚠️ Outil d'analyse factuelle — **pas un conseil en investissement**.

## Modifier ma liste
Éditer `watchlist.txt` (un symbole `EXCHANGE:SYMBOL` par ligne). Le déploiement se
relance tout seul (push) ou chaque jour (cron), ou via *Actions → Run workflow*.

## Lancer en local
```bash
pip install -r requirements.txt
python scripts/batch_charts.py watchlist.txt --out public --pwa --title "Analyse Tickers"
# puis servir le dossier public/ :  python -m http.server --directory public
```

## Déploiement
GitHub Actions (`.github/workflows/build.yml`) génère `public/` et le publie sur
GitHub Pages à chaque push, chaque jour (06:00 UTC), et à la demande.
Pré-requis une fois : *Settings → Pages → Source = GitHub Actions*.

Le site est en `noindex` (non référencé). Sur Pages gratuit l'URL reste toutefois
accessible si on la connaît (pas d'authentification).
