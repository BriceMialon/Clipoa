"""
Mises à jour automatiques de Clipoa installé par packaging/install.sh.

Disposition d'une installation (dossier CLIPOA_HOME, par défaut ~/Library/Clipoa) :
  app -> versions/<v>                 lien symbolique basculé à chaque mise à jour
  versions/<v>/release.json           {"version", "update_url", "platform"}
  versions/<v>/{storage,runtime,venv} liens vers data/storage, data/runtime, venv (partagés entre versions)
  tools/uv/uv                         installe les dépendances Python
  bin/clipoa-server                   relance le serveur quand il sort avec le code 42

Sans release.json (copie de développement git), les mises à jour sont désactivées.
Le paquet téléchargé est vérifié par son SHA-256 annoncé dans latest.json (HTTPS obligatoire).
"""

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests

from config import BASE_DIR

RESTART_EXIT_CODE = 42
CHECK_TTL_S = 3600
SHARED_LINKS = {"storage": "../../data/storage", "runtime": "../../data/runtime", "venv": "../../venv"}

_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {"at": 0.0, "info": None}
_STATE: Dict[str, Any] = {"running": False, "step": "", "progress": 0, "error": "", "done": False, "version": ""}


def parse_version(v: str) -> Tuple[int, ...]:
    out = []
    for part in str(v or "0").strip().lstrip("v").split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num or 0))
    return tuple(out)


def release_info(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    try:
        return json.loads((Path(base_dir or BASE_DIR) / "release.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def install_home(base_dir: Optional[Path] = None) -> Optional[Path]:
    """Dossier d'installation, ou None pour une copie de développement."""
    base = Path(base_dir or BASE_DIR).resolve()
    if base.parent.name == "versions" and (base.parent.parent / "app").is_symlink():
        return base.parent.parent
    return None


def _update_url(rel: Dict[str, Any]) -> str:
    return (os.getenv("CLIPOA_UPDATE_URL") or rel.get("update_url") or "").strip().rstrip("/")


def safe_url(url: str) -> bool:
    """HTTPS obligatoire ; HTTP accepté seulement sur la machine (tests locaux)."""
    p = urlparse(url or "")
    if p.scheme == "https" and p.hostname:
        return True
    return p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost")


def enabled() -> bool:
    rel = release_info()
    return bool(rel.get("version")) and install_home() is not None and safe_url(_update_url(rel))


def check(force: bool = False) -> Dict[str, Any]:
    rel = release_info()
    current = rel.get("version") or ""
    info: Dict[str, Any] = {"enabled": enabled(), "current": current, "available": False, "latest": current, "notes": ""}
    if not info["enabled"]:
        return info
    now = time.time()
    if not force and _CACHE["info"] and now - _CACHE["at"] < CHECK_TTL_S:
        return _CACHE["info"]
    try:
        r = requests.get(_update_url(rel) + "/latest.json", timeout=10)
        r.raise_for_status()
        latest = r.json()
        info["latest"] = str(latest.get("version") or current)
        info["notes"] = str(latest.get("notes") or "")[:600]
        info["available"] = parse_version(info["latest"]) > parse_version(current) and latest.get("platform", rel.get("platform")) == rel.get("platform")
    except Exception as e:  # hors ligne : on réessaiera plus tard
        info["error"] = f"Vérification impossible : {str(e)[:120]}"
    _CACHE.update(at=now, info=info)
    return info


def _download(url: str, dest: Path, expected_sha: str) -> None:
    h = hashlib.sha256()
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if total:
                    _STATE["progress"] = max(1, min(60, int(60 * done / total)))
    if h.hexdigest().lower() != (expected_sha or "").lower():
        dest.unlink(missing_ok=True)
        raise RuntimeError("le fichier téléchargé est corrompu (empreinte SHA-256 différente)")


def safe_extract(archive: Path, dest: Path) -> None:
    """Extrait sans jamais écrire hors de dest (chemins absolus, .., liens sortants refusés)."""
    dest = dest.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        for m in tar.getmembers():
            target = (dest / m.name).resolve()
            if target != dest and dest not in target.parents:
                raise RuntimeError(f"chemin interdit dans le paquet : {m.name}")
            if m.issym() or m.islnk():
                link = (target.parent / m.linkname).resolve() if m.issym() else (dest / m.linkname).resolve()
                if link != dest and dest not in link.parents:
                    raise RuntimeError(f"lien interdit dans le paquet : {m.name}")
            if m.isdev() or m.isfifo():
                raise RuntimeError(f"fichier spécial interdit : {m.name}")
        tar.extractall(dest)


def link_shared(version_dir: Path) -> None:
    for name, target in SHARED_LINKS.items():
        p = version_dir / name
        if p.is_symlink() or p.exists():
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                p.unlink()
        p.symlink_to(target)


def switch_current(home: Path, version: str) -> None:
    """Bascule atomique du lien app -> versions/<version>."""
    tmp = home / "app.new"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(Path("versions") / version)
    os.replace(tmp, home / "app")


def prune_versions(home: Path, keep: Tuple[str, ...]) -> None:
    for d in (home / "versions").iterdir():
        if d.is_dir() and d.name not in keep:
            shutil.rmtree(d, ignore_errors=True)


def _install_requirements(home: Path, req: Path) -> None:
    py = home / "venv" / "bin" / "python"
    uv = home / "tools" / "uv" / "uv"
    if uv.exists():
        cmd = [str(uv), "pip", "install", "-q", "--python", str(py), "-r", str(req)]
    else:
        cmd = [str(py), "-m", "pip", "install", "-q", "-r", str(req)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if res.returncode != 0:
        raise RuntimeError("installation des dépendances impossible : " + (res.stderr or res.stdout)[-300:])


def _apply(info: Dict[str, Any]) -> None:
    home = install_home()
    rel = release_info()
    base = _update_url(rel)
    r = requests.get(base + "/latest.json", timeout=15)
    r.raise_for_status()
    latest = r.json()
    version = str(latest["version"])
    if not version.replace(".", "").isalnum():
        raise RuntimeError("numéro de version invalide")
    url = urljoin(base + "/", str(latest["url"]))
    if not safe_url(url):
        raise RuntimeError("adresse de téléchargement non sécurisée")
    updates = home / "data" / "updates"
    updates.mkdir(parents=True, exist_ok=True)
    archive = updates / f"clipoa-{version}.tar.gz"
    _STATE.update(step="Téléchargement de la nouvelle version…", progress=1)
    _download(url, archive, str(latest.get("sha256") or ""))

    _STATE.update(step="Installation…", progress=65)
    versions = home / "versions"
    tmp_dir = versions / f".tmp-{version}"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True)
    safe_extract(archive, tmp_dir)
    if release_info(tmp_dir).get("version") != version:
        raise RuntimeError("le paquet ne correspond pas à la version annoncée")
    link_shared(tmp_dir)

    old_req = BASE_DIR / "requirements.txt"
    new_req = tmp_dir / "requirements.txt"
    if new_req.exists() and (not old_req.exists() or old_req.read_bytes() != new_req.read_bytes()):
        _STATE.update(step="Mise à jour des outils…", progress=75)
        _install_requirements(home, new_req)

    final_dir = versions / version
    if final_dir.exists():
        shutil.rmtree(final_dir)
    tmp_dir.rename(final_dir)
    switch_current(home, version)
    prune_versions(home, keep=(version, Path(BASE_DIR).resolve().name))
    archive.unlink(missing_ok=True)
    _STATE.update(step="Mise à jour installée. Redémarrage…", progress=100, done=True, version=version)
    _CACHE.update(at=0.0, info=None)


def start_update() -> Dict[str, Any]:
    if not enabled():
        return {"ok": False, "error": "Mises à jour indisponibles sur cette copie de Clipoa."}
    with _LOCK:
        if _STATE["running"]:
            return {"ok": True, "already": True}
        _STATE.update(running=True, step="Préparation…", progress=0, error="", done=False, version="")

    def _run():
        try:
            _apply(check(force=True))
            if os.getenv("CLIPOA_LAUNCHER") == "1":
                threading.Timer(1.5, lambda: os._exit(RESTART_EXIT_CODE)).start()
            else:
                _STATE["step"] = "Mise à jour installée. Relance Clipoa pour l'utiliser."
        except Exception as e:
            _STATE["error"] = f"Mise à jour impossible : {str(e)[:200]}"
            home = install_home()
            if home:
                for d in (home / "versions").glob(".tmp-*"):
                    shutil.rmtree(d, ignore_errors=True)
        finally:
            _STATE["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True}


def register(app) -> None:
    from flask import jsonify, request

    @app.route("/api/update/status", methods=["GET"])
    def update_status():
        info = check(force=request.args.get("force") == "1")
        return jsonify({**info, "state": dict(_STATE)})

    @app.route("/api/update/apply", methods=["POST"])
    def update_apply():
        res = start_update()
        return jsonify(res), (200 if res.get("ok") else 400)
