"""Renomme la marque visible « Clipoa » en « ClipRoll » dans les fichiers texte suivis par Git.

Rejouable sans risque (idempotent) sur n'importe quelle branche : `python tools/rebrand_cliproll.py`.
Ne touche PAS aux identifiants techniques, pour ne rien casser chez les utilisateurs déjà installés :
variables CLIPOA_*, clés localStorage clipoa_*, noms de fichiers clipoa_*.js, ~/Library/Clipoa,
~/.clipoa (clé du coffre), en-tête X-Clipoa-Token, identité Store « BriceMialon.Clipoa »,
Workers Cloudflare et URLs de callback OAuth (clipoa-oauth.clipoa-studio.workers.dev).
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".glb", ".blend", ".mp4", ".mp3", ".wav",
               ".woff", ".woff2", ".ttf", ".zip", ".gz", ".pdf", ".webp"}
SKIP_FILES = {"tools/rebrand_cliproll.py"}
# « Clipoa » mot entier, sauf dans les chemins/identifiants techniques ci-dessus.
PATTERN = re.compile(r"(?<!Library/)(?<!X-)(?<!BriceMialon\.)\bClipoa\b")
EXTRA = [("download_name=f\"clipoa_{render_id}.mp4\"", "download_name=f\"cliproll_{render_id}.mp4\"")]


def main() -> int:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    changed = 0
    for rel in files:
        p = ROOT / rel
        if rel in SKIP_FILES or p.suffix.lower() in SKIP_SUFFIX or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = PATTERN.sub("ClipRoll", text)
        for a, b in EXTRA:
            new = new.replace(a, b)
        if new != text:
            p.write_text(new, encoding="utf-8")
            changed += 1
            print(rel)
    print(f"{changed} fichier(s) modifié(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
