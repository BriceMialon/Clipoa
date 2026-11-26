#!/bin/bash
# Lancé par ClipRoll.app (DMG). 1er lancement : installe ClipRoll dans ~/Library/Clipoa (même script que la commande
# Terminal, embarqué et signé dans l'app) en affichant la progression dans le navigateur. Ensuite : ouvre ClipRoll.
# Les mises à jour se font dans ~/Library/Clipoa (bouton « Mettre à jour ») : l'app signée n'est jamais modifiée.
RES="$(cd "$(dirname "$0")" && pwd)"
H="${CLIPOA_HOME:-$HOME/Library/Clipoa}"
if [ -x "$H/bin/clipoa" ] && [ -L "$H/app" ]; then
  exec "$H/bin/clipoa"
fi
mkdir -p "$H/data/logs"
export CLIPOA_NO_APP=1                      # l'app est déjà dans /Applications
export CLIPOA_PROGRESS_HTML="$H/data/logs/installation.html"
printf '<meta charset="utf-8"><meta http-equiv="refresh" content="2"><body style="font:16px -apple-system;padding:40px">Préparation de ClipRoll…</body>' > "$CLIPOA_PROGRESS_HTML"
open "$CLIPOA_PROGRESS_HTML"
exec /bin/bash "$RES/install.sh" >>"$H/data/logs/installation.log" 2>&1
