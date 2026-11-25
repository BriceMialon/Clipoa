#!/usr/bin/env bash
set -e

# Se placer dans le dossier du projet
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "========================================================"
echo "🎬 Lancement de Clipoa..."
echo "========================================================"

# Vérifier si l'environnement virtuel existe
if [ ! -f "$DIR/venv/bin/python" ]; then
    echo "Création de l'environnement virtuel Python..."
    python3 -m venv "$DIR/venv"
    "$DIR/venv/bin/pip" install flask rich yt-dlp edge-tts requests faster-whisper imageio-ffmpeg
fi

# Installer automatiquement Node portable + Gemini CLI pour la connexion Google sans clé API
if [ ! -f "$DIR/runtime/gemini/bin/gemini" ] && [ "$(uname -s)" = "Darwin" ]; then
    ARCH="$(uname -m)"
    NODE_ARCH="arm64"
    [ "$ARCH" = "x86_64" ] && NODE_ARCH="x64"
    echo "Installation automatique du connecteur Google Gemini..."
    mkdir -p "$DIR/runtime"
    curl -sL "https://nodejs.org/dist/v22.14.0/node-v22.14.0-darwin-${NODE_ARCH}.tar.gz" | tar -xz -C "$DIR/runtime"
    mv "$DIR/runtime/node-v22.14.0-darwin-${NODE_ARCH}" "$DIR/runtime/node"
    export PATH="$DIR/runtime/node/bin:$PATH"
    npm install -g --prefix "$DIR/runtime/gemini" @google/gemini-cli >/dev/null 2>&1 || true
fi

# Ouvrir le navigateur après 1 seconde
(sleep 1 && open "http://localhost:8080" 2>/dev/null || true) &

# Lancer le serveur
exec "$DIR/venv/bin/python" "$DIR/app.py"
