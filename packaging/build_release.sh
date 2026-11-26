#!/usr/bin/env bash
# Fabrique une version installable de Clipoa (Mac Apple Silicon), code compilé avec Nuitka.
#   packaging/build_release.sh 0.1.0 "Notes de version" [--edition public|perso] [--update-url https://…]
# Résultat dans dist/ : clipoa-<v>-macos-arm64.tar.gz, latest.json, install.sh (à mettre en ligne tels quels).
# Seuls les fichiers COMMITÉS sont embarqués (git archive HEAD) : storage/, clés et venv n'y vont jamais.
set -euo pipefail

VERSION="${1:?usage: build_release.sh <version> [notes] [--edition public] [--update-url URL]}"
NOTES="${2:-}"
shift $(( $# >= 2 ? 2 : 1 ))
EDITION="public"
UPDATE_URL="${CLIPOA_UPDATE_URL:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --edition) EDITION="$2"; shift 2 ;;
    --update-url) UPDATE_URL="$2"; shift 2 ;;
    *) echo "option inconnue : $1" >&2; exit 2 ;;
  esac
done
case "$VERSION" in *[!0-9.]*) echo "version invalide" >&2; exit 2 ;; esac
[ -n "$UPDATE_URL" ] || { echo "donne --update-url (adresse où seront hébergés latest.json et le paquet)" >&2; exit 2; }
UPDATE_URL="${UPDATE_URL%/}"
[ "$(uname -s)-$(uname -m)" = "Darwin-arm64" ] || { echo "à lancer sur un Mac Apple Silicon" >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"
B="$(mktemp -d /tmp/clipoa_build.XXXX)"
SRC="$B/src"
PY_VERSION="3.9"
BLENDER_VERSION="${CLIPOA_BLENDER_VERSION:-5.3.0}"   # version testée avec Clipoa (voir CLAUDE.md)
UV="$(command -v uv || echo "$ROOT/venv/bin/uv")"
[ -x "$UV" ] || { echo "uv introuvable (pip install uv)" >&2; exit 2; }
command -v clang >/dev/null || { echo "clang manquant : xcode-select --install" >&2; exit 2; }

echo "▸ Copie du code commité ($(git -C "$ROOT" rev-parse --short HEAD))"
[ -z "$(git -C "$ROOT" status --porcelain -- core agents app.py config.py templates static assets requirements.txt)" ] || \
  echo "  ⚠️  des fichiers modifiés non commités sont ignorés"
mkdir -p "$SRC"
git -C "$ROOT" archive --format=tar HEAD | tar -x -C "$SRC"
cd "$SRC"
rm -rf tests docs site_public backups_multicomptes oauth_relay_worker.js cli.py ./*.command ./*.md packaging

echo "▸ Environnement de compilation (Python $PY_VERSION + Nuitka)"
UV_PYTHON_PREFERENCE=only-managed "$UV" python install --no-bin "$PY_VERSION" >/dev/null
UV_PYTHON_PREFERENCE=only-managed "$UV" venv -q --python "$PY_VERSION" "$B/venv"
"$UV" pip install -q --python "$B/venv/bin/python" "nuitka>=2.5,<3" ordered-set zstandard
"$UV" pip install -q --python "$B/venv/bin/python" -r requirements.txt   # Nuitka doit voir les mêmes paquets
echo "▸ Verrou des dépendances (versions + empreintes)"
"$UV" pip compile -q requirements.txt --generate-hashes --python-version "$PY_VERSION" --python-platform aarch64-apple-darwin -o requirements.lock
NUITKA=("$B/venv/bin/python" -m nuitka --module --no-pyi-file --remove-output --output-dir="$B/out" --assume-yes-for-downloads)

echo "▸ Compilation de core/ et agents/ (plusieurs minutes)"
touch core/__init__.py agents/__init__.py
"${NUITKA[@]}" core --include-package=core --nofollow-import-to=core.blender_kit,core.tts_worker,core.cine_engine
"${NUITKA[@]}" agents --include-package=agents

echo "▸ Compilation de app.py"
mv app.py clipoa_app.py
"${NUITKA[@]}" clipoa_app.py

echo "▸ Assemblage"
# on retire les sources compilées ; restent les scripts lus par Blender / le worker voix et les données
find core agents -maxdepth 1 -name '*.py' -delete
rm -f clipoa_app.py
find . -name '__pycache__' -prune -exec rm -rf {} +
cp "$B"/out/*.so .
codesign -s - -f ./*.so >/dev/null 2>&1 || true
cat > app.py <<'EOS'
"""Lanceur de Clipoa (le code de l'application est compilé)."""
import os
import threading

import clipoa_app

if __name__ == "__main__":
    try:
        from core import tools_setup
        threading.Thread(target=tools_setup.auto_setup_on_launch, daemon=True).start()
    except Exception as _e:
        print(f"Outils : {_e}")
    clipoa_app.run_app(port=int(os.getenv("CLIPOA_PORT", "8080")))
EOS
printf '%s\n' "$EDITION" > edition
cat > release.json <<EOS
{"version": "$VERSION", "update_url": "$UPDATE_URL", "platform": "macos-arm64", "edition": "$EDITION",
 "commit": "$(git -C "$ROOT" rev-parse --short HEAD)", "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
EOS

echo "▸ Vérification : le serveur compilé s'importe"
ln -s "$B/venv" venv
mkdir -p "$B/check_storage" && ln -s "$B/check_storage" storage
CLIPOA_NO_AUTO_TOOLS=1 "$B/venv/bin/python" -c "import clipoa_app, core.updater; print('  ok', clipoa_app.app.name)"
rm -f venv storage
leftover="$(find core agents -maxdepth 1 -name '*.py' | head -3)"
[ -z "$leftover" ] || { echo "sources restantes : $leftover" >&2; exit 1; }

echo "▸ Blender $BLENDER_VERSION (empreinte officielle blender.org)"
BL_DIR="https://download.blender.org/release/Blender${BLENDER_VERSION%.*}"
BL_FILE="blender-$BLENDER_VERSION-macos-arm64.dmg"
BL_SHA="$(curl -fsSL "$BL_DIR/blender-$BLENDER_VERSION.sha256" | awk -v f="$BL_FILE" '$2==f {print $1}')"
[ -n "$BL_SHA" ] || { echo "empreinte de $BL_FILE introuvable sur blender.org" >&2; exit 1; }

WH_REV="$(curl -fsSL https://huggingface.co/api/models/Systran/faster-whisper-base/revision/main | "$B/venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["sha"])')"
[ -n "$WH_REV" ] || { echo "révision Whisper introuvable" >&2; exit 1; }

mkdir -p "$DIST"
PKG="clipoa-$VERSION-macos-arm64.tar.gz"
tar -czf "$DIST/$PKG" -C "$SRC" .
SHA="$(shasum -a 256 "$DIST/$PKG" | cut -d' ' -f1)"
NOTES_JSON="$("$B/venv/bin/python" -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$NOTES")"
cat > "$DIST/latest.json" <<EOS
{"version": "$VERSION", "platform": "macos-arm64", "url": "$PKG", "sha256": "$SHA",
 "size": $(stat -f%z "$DIST/$PKG"), "notes": $NOTES_JSON,
 "blender_version": "$BLENDER_VERSION", "blender_url": "$BL_DIR/$BL_FILE", "blender_sha256": "$BL_SHA",
 "whisper_revision": "$WH_REV"}
EOS
sed "s#__CLIPOA_UPDATE_URL__#$UPDATE_URL#" "$ROOT/packaging/install.sh" > "$DIST/install.sh"
rm -rf "$B"
echo "✓ dist/$PKG ($(du -h "$DIST/$PKG" | cut -f1)), latest.json, install.sh"
