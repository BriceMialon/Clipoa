import csv
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from config import STORAGE_DIR
from core.settings_store import load_settings, save_settings

DRIVE_SYNC_DIR = STORAGE_DIR / "drive_sync" / "workspace"
DRIVE_SYNC_DIR.mkdir(parents=True, exist_ok=True)


class DriveClient:
    """
    Connects ClipRoll Studio to any local synced Google Drive or creative workspace folder, loading:
    - Creative Guides & Narrative Rules (guide_retention.md, SKILL.md, bible.md)
    - Asset & Voice Registry (bibliotheque.json)
    - Optional CSV Ideas Bank (idees.csv)
    """

    @classmethod
    def get_sync_dir(cls) -> Path:
        settings = load_settings()
        custom = settings.get("drive", {}).get("local_sync_dir")
        if custom:
            p = Path(custom).expanduser()
            p.mkdir(parents=True, exist_ok=True)
            return p
        return DRIVE_SYNC_DIR

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        settings = load_settings()
        drive_cfg = settings.get("drive", {})
        sync_dir = cls.get_sync_dir()

        files = []
        if sync_dir.exists():
            for f in sorted(sync_dir.iterdir()):
                if f.is_file() and not f.name.startswith("."):
                    files.append({
                        "name": f.name,
                        "size_kb": round(f.stat().st_size / 1024, 1),
                        "ext": f.suffix.lower(),
                    })

        bib = cls.load_bibliotheque()
        ideas = cls.load_ideas(limit=250)

        return {
            "connected": len(files) > 0,
            "folder_id": drive_cfg.get("folder_id", ""),
            "folder_name": drive_cfg.get("folder_name", "Mon dossier créatif"),
            "local_sync_dir": str(sync_dir),
            "last_sync": drive_cfg.get("last_sync") or "Synchronisé localement",
            "files_count": len(files),
            "files": files,
            "voices_count": len([k for k in (bib.get("voix") or {}).keys() if not k.startswith("_") and k not in ("reserve", "tons")]),
            "models_count": len(bib.get("personnages", {})) + len(bib.get("decors", {})) + len(bib.get("accessoires", {})),
            "ideas_count": len(ideas),
        }

    @classmethod
    def load_bibliotheque(cls) -> Dict[str, Any]:
        bib_path = cls.get_sync_dir() / "bibliotheque.json"
        if not bib_path.exists():
            return {}
        try:
            with open(bib_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @classmethod
    def load_ideas(cls, query: str = "", limit: int = 40) -> List[Dict[str, Any]]:
        csv_path = cls.get_sync_dir() / "200_idees.csv"
        if not csv_path.exists():
            return []
        ideas: List[Dict[str, Any]] = []
        q = query.strip().lower()
        try:
            with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                headers = next(reader, [])
                for idx, row in enumerate(reader, start=1):
                    cells = [c.strip() for c in row if c and c.strip()]
                    if len(cells) < 2:
                        continue
                    # Heuristic extraction across standard spreadsheet columns
                    title = ""
                    category = ""
                    status = ""
                    for c in cells:
                        if len(c) > len(title) and not c.startswith("http"):
                            title = c
                    if len(cells) >= 2:
                        category = cells[1] if cells[1] != title else (cells[0] if cells[0] != title else "Finance")
                    if len(cells) >= 4:
                        status = cells[-1] if len(cells[-1]) < 25 else ""

                    if not title or len(title) < 8:
                        continue
                    if q and q not in title.lower() and q not in category.lower():
                        continue
                    ideas.append({
                        "id": idx,
                        "title": title[:160],
                        "category": category[:40],
                        "status": status,
                    })
                    if len(ideas) >= limit:
                        break
        except Exception:
            return []
        return ideas

    @classmethod
    def get_workspace_context(cls) -> str:
        """
        Reads any synced local creative workspace guides (guide_retention.md, regles_description.md,
        SKILL.md, bibliotheque.json summary) to feed optional context into Claude.
        """
        sync_dir = cls.get_sync_dir()
        parts: List[str] = []

        for fname, label, max_chars in [
            ("guide_retention.md", "GUIDE RÉTENTION", 3500),
            ("regles_description.md", "RÈGLES DE DESCRIPTION", 1200),
            ("SKILL.md", "MÉTHODE DE PRODUCTION", 2500),
        ]:
            p = sync_dir / fname
            if p.exists():
                try:
                    txt = p.read_text(encoding="utf-8", errors="ignore").strip()
                    if txt:
                        parts.append(f"=== {label} ===\n{txt[:max_chars]}")
                except Exception:
                    pass

        bib = cls.load_bibliotheque()
        if bib:
            raw_voix = bib.get("voix") or {}
            if isinstance(raw_voix, dict):
                voix = {k: v.get("nom") for k, v in raw_voix.items() if isinstance(v, dict) and v.get("nom")}
            else:
                voix = raw_voix

            def _extract_names(val):
                if isinstance(val, dict):
                    return list(val.keys())[:20]
                if isinstance(val, list):
                    out = []
                    for item in val[:20]:
                        if isinstance(item, dict):
                            out.append(str(item.get("nom") or item.get("name") or item.get("id") or ""))
                        else:
                            out.append(str(item))
                    return [x for x in out if x]
                return []

            persos = _extract_names(bib.get("personnages"))
            decors = _extract_names(bib.get("decors"))
            parts.append(
                "=== BIBLIOTHÈQUE 3D & VOIX DISPONIBLES ===\n"
                f"Voix attribuées : {json.dumps(voix, ensure_ascii=False)}\n"
                f"Personnages 3D : {', '.join(persos)}\n"
                f"Décors 3D : {', '.join(decors)}"
            )

        return "\n\n".join(parts)

    @classmethod
    def sync_from_local_folder(cls, source_folder: str) -> Dict[str, Any]:
        """Copies relevant guides/models/JSON/CSV from a local Drive folder into drive_sync."""
        src = Path(source_folder).expanduser().resolve()
        if not src.exists() or not src.is_dir():
            raise FileNotFoundError(f"Dossier introuvable : {source_folder}")

        dest = cls.get_sync_dir()
        copied = 0
        allowed_ext = {".md", ".txt", ".json", ".csv", ".glb", ".fbx", ".blend", ".mp3", ".m4a", ".wav"}
        for item in src.rglob("*"):
            if item.is_file() and item.suffix.lower() in allowed_ext and item.stat().st_size < 150 * 1024 * 1024:
                target = dest / item.name
                shutil.copy2(item, target)
                copied += 1

        ts = time.strftime("%Y-%m-%d %H:%M")
        save_settings({"drive": {"local_sync_dir": str(dest), "last_sync": ts}})
        return {"synced_files": copied, "last_sync": ts, "status": cls.get_status()}
