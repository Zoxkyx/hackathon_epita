# Rapport final — `report.html`

Ouvrez `report.html` dans un navigateur (double-clic). Aucune installation nécessaire.

C'est un fichier autonome : pas de JS, pas de CSS séparé, tout est inline. La seule
dépendance externe est **Google Fonts** (Space Grotesk + JetBrains Mono) chargée via
un lien CDN dans le `<head>` — il faut être connecté à internet pour voir les bonnes
polices, sinon la page retombe simplement sur la police système (rien ne casse).

13 sections, chacune capturable isolément pour le PDF (voir `docs/architecture.md`
pour le détail de ce que chaque section démontre).

**Données** : ce rapport est généré depuis `scripts/demo_html_report.py`, un jeu de
données factice mais riche (révisions déclenchées, correction DriftWatcher, courbe
de rétention multi-points) — choisi pour être le meilleur matériel visuel pour le
PDF, pas un run réel contre l'API.

## Régénérer après une modification du code

```powershell
.venv\Scripts\python.exe scripts\demo_html_report.py
copy data\runs\demo-2026-09-03\report.html report\report.html
```
