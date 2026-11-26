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

  mkdir -p "$H"/{versions,data/storage,data/runtime,data/venv_tts,data/logs,data/updates,tools,bin}
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
    "$UV" python install --no-bin "$PY_VERSION" >/dev/null
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
    ln -sfn ../../data/venv_tts "$D/venv_tts"
    say "Installation des outils de Clipoa (quelques minutes la première fois)…"
    if [ -f "$D/requirements.lock" ]; then   # versions et empreintes figées au moment du build
      "$UV" pip install -q --require-hashes --python "$H/venv/bin/python" -r "$D/requirements.lock"
    else
      "$UV" pip install -q --python "$H/venv/bin/python" -r "$D/requirements.txt"
    fi
    rm -rf "$H/versions/$VERSION"; mv "$D" "$H/versions/$VERSION"
  fi
  # 3b. Blender (version fixée par Clipoa, téléchargé sur blender.org, gardé dans data/runtime : jamais re-téléchargé aux mises à jour)
  BL_VER="$(read_json blender_version 2>/dev/null || true)"
  if [ -n "$BL_VER" ] && [ "$(cat "$H/data/runtime/blender_version" 2>/dev/null)" != "$BL_VER" ]; then
    BL_URL="$(read_json blender_url)"; BL_SHA="$(read_json blender_sha256)"
    case "$BL_URL" in https://download.blender.org/*) ;; *) die "Adresse de Blender inattendue." ;; esac
    say "Téléchargement de Blender $BL_VER (environ 400 Mo, une seule fois)…"
    curl -fL --progress-bar "$BL_URL" -o "$TMP/blender.dmg"
    [ "$(shasum -a 256 "$TMP/blender.dmg" | cut -d' ' -f1)" = "$BL_SHA" ] || die "Blender téléchargé est corrompu."
    say "Installation de Blender…"
    MNT="$TMP/blender_mnt"; mkdir -p "$MNT"
    hdiutil attach "$TMP/blender.dmg" -nobrowse -quiet -mountpoint "$MNT"
    rm -rf "$H/data/runtime/Blender.app.new"
    cp -R "$MNT/Blender.app" "$H/data/runtime/Blender.app.new"
    hdiutil detach "$MNT" -quiet -force || true
    rm -rf "$H/data/runtime/Blender.app"; mv "$H/data/runtime/Blender.app.new" "$H/data/runtime/Blender.app"
    printf '%s\n' "$BL_VER" > "$H/data/runtime/blender_version"
    rm -f "$TMP/blender.dmg"
  fi
  # 3c. Modèle de transcription Whisper « base » (révision fixée, gardé dans data/runtime)
  WH_REV="$(read_json whisper_revision 2>/dev/null || true)"
  WH_DIR="$H/data/runtime/models/faster-whisper-base"
  if [ -n "$WH_REV" ] && [ "$(cat "$WH_DIR/.clipoa_revision" 2>/dev/null)" != "$WH_REV" ]; then
    say "Téléchargement du modèle de transcription (environ 150 Mo, une seule fois)…"
    rm -rf "$WH_DIR"
    HF_HUB_DISABLE_TELEMETRY=1 "$H/venv/bin/python" -c 'import sys; from huggingface_hub import snapshot_download; snapshot_download("Systran/faster-whisper-base", revision=sys.argv[1], local_dir=sys.argv[2])' "$WH_REV" "$WH_DIR" >/dev/null
    [ -f "$WH_DIR/model.bin" ] || die "Modèle de transcription incomplet."
    printf '%s\n' "$WH_REV" > "$WH_DIR/.clipoa_revision"
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
# tout ce que l'app télécharge reste dans le dossier Clipoa et survit aux mises à jour
export HF_HOME="$H/data/runtime/huggingface" HF_HUB_DISABLE_TELEMETRY=1
export PLAYWRIGHT_BROWSERS_PATH="$H/data/runtime/ms-playwright"
export CLIPOA_WHISPER_DIR="$H/data/runtime/models/faster-whisper-base"
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

  say "Clipoa $VERSION est installé. Ouverture…"
  say "Pour le rouvrir plus tard : application « Clipoa » dans le dossier Applications de ton compte."
  if pgrep -f "$H/bin/clipoa-server" >/dev/null 2>&1; then
    pkill -f "$H/bin/clipoa-server" || true; pkill -f "$H/venv/bin/python app.py" || true; sleep 1
  fi
  "$H/bin/clipoa"
}

main "$@"
