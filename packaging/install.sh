#!/usr/bin/env bash
# Installation de Clipoa sur Mac (Apple Silicon) :
#   curl -fsSL <adresse>/install.sh | bash
# Désinstaller : curl -fsSL <adresse>/install.sh | bash -s -- --uninstall   (garde tes vidéos ; --purge efface tout)
#
# Variables utiles (tests) : CLIPOA_UPDATE_URL (serveur des versions), CLIPOA_HOME (dossier d'installation),
# CLIPOA_PORT, CLIPOA_NO_OPEN=1 (ne pas ouvrir le navigateur), CLIPOA_NO_APP=1 (pas de raccourci dans ~/Applications).
# Tout le script est dans main() : rien ne s'exécute si le téléchargement est coupé en route.

main() {
  set -euo pipefail

  UPDATE_URL="${CLIPOA_UPDATE_URL:-__CLIPOA_UPDATE_URL__}"
  H="${CLIPOA_HOME:-$HOME/Library/Clipoa}"
  APP_BUNDLE="$HOME/Applications/Clipoa.app"
  UV_VERSION="0.13.10"
  PY_VERSION="3.9"

  say() { printf '\033[1;35m▸\033[0m %s\n' "$*"; }
  die() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

  if [ "${1:-}" = "--uninstall" ]; then
    say "Désinstallation de Clipoa…"
    pkill -f "$H/bin/clipoa-server" 2>/dev/null || true
    rm -rf "$APP_BUNDLE" "$H/app" "$H/app.new" "$H/versions" "$H/venv" "$H/python" "$H/tools" "$H/bin"
    if [ "${2:-}" = "--purge" ]; then rm -rf "$H"; say "Tout est effacé."; else say "Clipoa est retiré. Tes vidéos et réglages restent dans $H/data."; fi
    exit 0
  fi

  [ "$(uname -s)" = "Darwin" ] || die "Clipoa s'installe sur Mac pour l'instant."
  [ "$(uname -m)" = "arm64" ] || die "Cette version demande un Mac Apple Silicon (M1 ou plus récent). Les Mac Intel viendront plus tard."
  case "$UPDATE_URL" in
    https://*|http://127.0.0.1*|http://localhost*) ;;
    *) die "Adresse du serveur Clipoa manquante ou non sécurisée ($UPDATE_URL)." ;;
  esac
  UPDATE_URL="${UPDATE_URL%/}"

  mkdir -p "$H"/{versions,data/storage,data/runtime,data/logs,data/updates,tools,bin}
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT

  # 1. uv : installe Python et les dépendances sans rien toucher au reste du Mac
  UV="$H/tools/uv/uv"
  if [ ! -x "$UV" ]; then
    say "Téléchargement de l'installateur Python (uv $UV_VERSION)…"
    U="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-aarch64-apple-darwin.tar.gz"
    curl -fsSL "$U" -o "$TMP/uv.tgz"
    curl -fsSL "$U.sha256" -o "$TMP/uv.sha256"
    [ "$(shasum -a 256 "$TMP/uv.tgz" | cut -d' ' -f1)" = "$(cut -d' ' -f1 < "$TMP/uv.sha256")" ] || die "uv téléchargé est corrompu."
    mkdir -p "$H/tools/uv"
    tar -xzf "$TMP/uv.tgz" -C "$TMP"
    cp "$TMP/uv-aarch64-apple-darwin/uv" "$UV"
    chmod +x "$UV"
  fi
  export UV_PYTHON_INSTALL_DIR="$H/python" UV_CACHE_DIR="$H/data/cache/uv" UV_PYTHON_PREFERENCE=only-managed

  # 2. Python (même version mineure que celle qui a compilé Clipoa)
  if [ ! -x "$H/venv/bin/python" ]; then
    say "Installation de Python $PY_VERSION (dans $H, rien n'est modifié ailleurs)…"
    "$UV" python install "$PY_VERSION" >/dev/null
    "$UV" venv --seed --python "$PY_VERSION" "$H/venv" >/dev/null
  fi

  # 3. Dernière version de Clipoa
  say "Recherche de la dernière version de Clipoa…"
  curl -fsSL "$UPDATE_URL/latest.json" -o "$TMP/latest.json" || die "Serveur Clipoa injoignable ($UPDATE_URL)."
  read_json() { "$H/venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$TMP/latest.json" "$1"; }
  VERSION="$(read_json version)"; PKG="$(read_json url)"; SHA="$(read_json sha256)"
  case "$VERSION" in *[!0-9.]*|"") die "Numéro de version invalide." ;; esac
  case "$PKG" in http*) ;; *) PKG="$UPDATE_URL/$PKG" ;; esac

  if [ -e "$H/versions/$VERSION/release.json" ]; then
    say "Clipoa $VERSION est déjà installé."
  else
    say "Téléchargement de Clipoa $VERSION…"
    curl -fL --progress-bar "$PKG" -o "$TMP/clipoa.tgz"
    [ "$(shasum -a 256 "$TMP/clipoa.tgz" | cut -d' ' -f1)" = "$SHA" ] || die "Le paquet téléchargé est corrompu."
    D="$H/versions/.tmp-$VERSION"
    rm -rf "$D"; mkdir -p "$D"
    # refuse les chemins absolus ou qui remontent (..)
    if tar -tzf "$TMP/clipoa.tgz" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then die "Paquet invalide."; fi
    tar -xzf "$TMP/clipoa.tgz" -C "$D"
    ln -sfn ../../data/storage "$D/storage"
    ln -sfn ../../data/runtime "$D/runtime"
    ln -sfn ../../venv "$D/venv"
    say "Installation des outils de Clipoa (quelques minutes la première fois)…"
    "$UV" pip install -q --python "$H/venv/bin/python" -r "$D/requirements.txt"
    rm -rf "$H/versions/$VERSION"; mv "$D" "$H/versions/$VERSION"
  fi
  ln -sfn "versions/$VERSION" "$H/app.new" && mv -fh "$H/app.new" "$H/app"

  # 4. Lanceurs
  cat > "$H/bin/clipoa-server" <<'EOS'
#!/bin/bash
# Serveur Clipoa ; relancé tout seul après une mise à jour (code de sortie 42).
H="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$H/data/logs/clipoa.log"
[ -f "$LOG" ] && [ "$(stat -f%z "$LOG")" -gt 20000000 ] && mv -f "$LOG" "$LOG.1"
export CLIPOA_LAUNCHER=1 CLIPOA_PORT="${CLIPOA_PORT:-8080}"
export CLIPOA_EDITION="$(cat "$H/app/edition" 2>/dev/null || echo public)"
while :; do
  cd "$H/app" || exit 1
  "$H/venv/bin/python" app.py >>"$LOG" 2>&1
  [ $? -eq 42 ] || break
  echo "--- redémarrage après mise à jour ---" >>"$LOG"
done
EOS
  cat > "$H/bin/clipoa" <<'EOS'
#!/bin/bash
# Ouvre Clipoa (démarre le serveur s'il ne tourne pas).
H="$(cd "$(dirname "$0")/.." && pwd)"
URL="http://localhost:${CLIPOA_PORT:-8080}"
if ! curl -fs -o /dev/null --max-time 2 "$URL/api/update/status"; then
  nohup "$H/bin/clipoa-server" >/dev/null 2>&1 &
  for _ in $(seq 1 120); do curl -fs -o /dev/null --max-time 1 "$URL/api/update/status" && break; sleep 0.5; done
fi
[ -n "${CLIPOA_NO_OPEN:-}" ] || open "$URL"
EOS
  chmod +x "$H/bin/clipoa" "$H/bin/clipoa-server"

  # 5. Application « Clipoa » dans ~/Applications (créée ici, donc pas bloquée par Gatekeeper)
  if [ -z "${CLIPOA_NO_APP:-}" ]; then
    mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"
    printf '#!/bin/bash\nexec "%s/bin/clipoa"\n' "$H" > "$APP_BUNDLE/Contents/MacOS/Clipoa"
    chmod +x "$APP_BUNDLE/Contents/MacOS/Clipoa"
    [ -f "$H/app/assets/clipoa.icns" ] && cp "$H/app/assets/clipoa.icns" "$APP_BUNDLE/Contents/Resources/clipoa.icns"
    cat > "$APP_BUNDLE/Contents/Info.plist" <<EOS
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Clipoa</string>
  <key>CFBundleIdentifier</key><string>app.clipoa.launcher</string>
  <key>CFBundleExecutable</key><string>Clipoa</string>
  <key>CFBundleIconFile</key><string>clipoa</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>LSUIElement</key><true/>
</dict></plist>
EOS
  fi

  say "Clipoa $VERSION est installé. Ouverture… (Blender se télécharge tout seul au premier lancement)"
  say "Pour le rouvrir plus tard : application « Clipoa » dans le dossier Applications de ton compte."
  if pgrep -f "$H/bin/clipoa-server" >/dev/null 2>&1; then
    pkill -f "$H/bin/clipoa-server" || true; pkill -f "$H/venv/bin/python app.py" || true; sleep 1
  fi
  "$H/bin/clipoa"
}

main "$@"
