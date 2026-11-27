"""
Pilote auto (ex « Mode Nuit ») : prépare un lot de vidéos (la semaine) puis les programme.

Fonctionnement :
1. Chaque sujet devient une tâche « pending ». À l'heure choisie (ou tout de suite), le worker lance
   UNE fabrication à la fois par le circuit normal (`/api/make` : Claude, réglages de Créer, protection
   CPU, pause/reprise quota, notification) — c'est `app.py` qui fournit ce lanceur via `configure()`.
2. La tâche suit son job (progression, pause quota, erreur). Vidéo prête → « waiting_validation ».
3. Règle d'or : rien n'est publié sans accord. Une vidéo n'est programmée (date du créneau Lun→Ven)
   qu'une fois VALIDÉE par l'utilisateur dans ClipRoll. Sans réseau choisi, elle reste dans Mes vidéos.
"""
import atexit
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from config import STORAGE_DIR, RENDERS_DIR, DEFAULT_THEME, DEFAULT_SUBTITLE_STYLE

NIGHT_QUEUE_FILE = STORAGE_DIR / "night_factory.json"
_LOCK = threading.RLock()

ACTIVE_JOB_STATUSES = ("running", "paused_quota", "paused_restart")
DEFAULT_PUBLISH_TIME = "18:00"


def _parse_hhmm(raw: str) -> Optional[tuple]:
    try:
        h, m = str(raw or "").strip().split(":")[:2]
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (TypeError, ValueError):
        pass
    return None


def week_slots(count: int, publish_time: str = DEFAULT_PUBLISH_TIME, today: Optional[datetime] = None) -> List[str]:
    """Créneaux Lun→Ven de la semaine qui vient (lundi strictement après aujourd'hui), à l'heure donnée."""
    hm = _parse_hhmm(publish_time) or _parse_hhmm(DEFAULT_PUBLISH_TIME)
    base = (today or datetime.now()).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    days_to_monday = (7 - base.weekday()) % 7 or 7
    monday = base + timedelta(days=days_to_monday)
    return [(monday + timedelta(days=i % 5 + 7 * (i // 5))).strftime("%Y-%m-%dT%H:%M") for i in range(max(0, count))]


def next_free_slot(wanted: str, now: Optional[datetime] = None) -> str:
    """Si le créneau prévu est passé (vidéo validée en retard) : prochain jour de semaine, même heure."""
    now = now or datetime.now()
    try:
        iso = str(wanted or "").strip()
        if iso.endswith("Z"):
            iso = iso[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
    except (TypeError, ValueError):
        return wanted
    while dt <= now + timedelta(minutes=5) or dt.weekday() >= 5:
        dt += timedelta(days=1)
    return dt.strftime("%Y-%m-%dT%H:%M")


class NightFactory:
    _worker_started = False
    _stop_flag = False
    _caffeinate_proc: Optional[subprocess.Popen] = None

    # Fournis par app.py (configure) : lanceur de fabrication et lecteur d'état des jobs.
    _launcher: Optional[Callable[[Dict[str, Any]], str]] = None
    _job_reader: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None
    _scheduler: Optional[Callable[[Dict[str, Any], Dict[str, Any], str], str]] = None

    @classmethod
    def configure(cls, launcher=None, job_reader=None, scheduler=None):
        if launcher is not None:
            cls._launcher = launcher
        if job_reader is not None:
            cls._job_reader = job_reader
        if scheduler is not None:
            cls._scheduler = scheduler

    # ------------------------------------------------------------------ stockage
    @classmethod
    def load_tasks(cls) -> List[Dict[str, Any]]:
        with _LOCK:
            if not NIGHT_QUEUE_FILE.exists():
                return []
            try:
                with open(NIGHT_QUEUE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, list) else []
            except Exception:
                return []

    @classmethod
    def save_tasks(cls, tasks: List[Dict[str, Any]]):
        with _LOCK:
            NIGHT_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(NIGHT_QUEUE_FILE.parent), prefix=".night_", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(tasks, f, indent=2, ensure_ascii=False)
                os.replace(tmp, NIGHT_QUEUE_FILE)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

    @classmethod
    def _mutate(cls, fn: Callable[[List[Dict[str, Any]]], Any]):
        """Lecture → modification → écriture sous un seul verrou (plus de mise à jour perdue)."""
        with _LOCK:
            tasks = cls.load_tasks()
            out = fn(tasks)
            cls.save_tasks(tasks)
            return out

    # ------------------------------------------------------------------ API
    @classmethod
    def enqueue_batch(
        cls,
        topics: List[str],
        plugin_id: Optional[str] = None,
        target_duration_sec: int = 60,
        start_at: str = "",
        theme: str = DEFAULT_THEME,
        subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
        voice: Optional[str] = None,
        keep_awake: bool = True,
        publish_platforms: Optional[List[str]] = None,
        publish_time: str = DEFAULT_PUBLISH_TIME,
        account: Optional[str] = None,
        **_ignored,
    ) -> List[Dict[str, Any]]:
        """`_ignored` absorbe les anciens paramètres (engine, model, auto_publish_platforms) : Claude écrit
        toujours les scripts et aucune publication immédiate sans validation n'est possible."""
        clean = [str(t).strip()[:200] for t in (topics or []) if str(t).strip()]
        plats = [str(p).strip().lower() for p in (publish_platforms or []) if str(p).strip()]
        slots = week_slots(len(clean), publish_time) if plats else [""] * len(clean)
        batch_id = f"week_{uuid.uuid4().hex[:6]}"
        created: List[Dict[str, Any]] = []
        for i, topic in enumerate(clean):
            created.append({
                "id": f"night_{uuid.uuid4().hex[:8]}",
                "batch_id": batch_id,
                "topic": topic,
                "plugin_id": (plugin_id or "").strip(),
                "target_duration_sec": max(15, min(180, int(target_duration_sec or 60))),
                "start_at": (start_at or "").strip(),
                "theme": theme,
                "subtitle_style": subtitle_style,
                "voice": voice or "",
                "keep_awake": bool(keep_awake),
                "account": account or "",
                "publish_platforms": plats,
                "publish_at": slots[i],
                "post_id": "",
                "job_id": "",
                "status": "pending",
                "progress": 0,
                "step": "En attente",
                "session_id": "",
                "error": "",
                "created_at": time.strftime("%Y-%m-%d %H:%M"),
            })
        cls._mutate(lambda tasks: tasks.extend(created))
        cls.start_worker()
        return created

    @classmethod
    def clear_completed(cls):
        keep = ("pending", "running", "waiting_validation")

        def _fn(tasks):
            tasks[:] = [t for t in tasks if t.get("status") in keep]
        cls._mutate(_fn)

    @classmethod
    def cancel_task(cls, task_id: str):
        """En attente → retirée. En cours → marquée annulée : la fabrication en cours se termine
        (elle reste dans Mes vidéos) mais rien ne sera programmé pour elle."""
        def _fn(tasks):
            for t in list(tasks):
                if t.get("id") != task_id:
                    continue
                if t.get("status") == "running":
                    t["status"] = "cancelled"
                    t["step"] = "Annulée : la fabrication en cours se termine, rien ne sera programmé."
                else:
                    tasks.remove(t)
        cls._mutate(_fn)

    # ------------------------------------------------------------------ anti-veille
    @classmethod
    def _set_awake(cls, active: bool):
        if sys.platform != "darwin":
            return
        if active:
            if cls._caffeinate_proc is None or cls._caffeinate_proc.poll() is not None:
                try:
                    cls._caffeinate_proc = subprocess.Popen(["caffeinate", "-i"])
                except Exception:
                    pass
        else:
            if cls._caffeinate_proc is not None and cls._caffeinate_proc.poll() is None:
                try:
                    cls._caffeinate_proc.terminate()
                except Exception:
                    pass
            cls._caffeinate_proc = None

    # ------------------------------------------------------------------ boucle
    @staticmethod
    def _render_meta(session_id: str) -> Optional[Dict[str, Any]]:
        if not session_id or "/" in session_id or ".." in session_id:
            return None
        d = RENDERS_DIR / session_id
        if not (d / "final_short.mp4").exists():
            return None
        try:
            return json.loads((d / "metadata.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    @classmethod
    def _default_scheduler(cls, task: Dict[str, Any], meta: Dict[str, Any], when: str) -> str:
        from core.social_publisher import FreeSocialPublisher
        sid = task["session_id"]
        for p in FreeSocialPublisher.load_queue():
            if p.get("render_id") == sid and p.get("status") in ("scheduled", "publishing", "published"):
                return p.get("id") or "manual"  # déjà programmée / publiée à la main : pas de doublon
        script = meta.get("script") or {}
        post = FreeSocialPublisher.create_post(
            render_id=sid,
            video_path=str(RENDERS_DIR / sid / "final_short.mp4"),
            title=script.get("title") or meta.get("title") or task.get("topic", ""),
            caption=meta.get("social_caption") or script.get("social_caption") or "",
            platforms=task.get("publish_platforms") or [],
            scheduled_at=when,
            publish_now=False,
        )
        return post.get("id", "")

    @classmethod
    def tick(cls, now: Optional[datetime] = None) -> None:
        """Un passage du worker (appelé toutes les 10 s ; testable directement)."""
        now = now or datetime.now()
        reader, launcher = cls._job_reader, cls._launcher
        scheduler = cls._scheduler or cls._default_scheduler

        def _fn(tasks):
            busy = False
            # 1. Suivre les fabrications lancées
            for t in tasks:
                jid = t.get("job_id")
                if not jid or t.get("status") not in ("running", "cancelled"):
                    continue
                job = reader(jid) if reader else None
                if job is None:
                    if t["status"] == "running":
                        t.update(status="error", error="Fabrication introuvable (supprimée de la liste ?)",
                                 step="❌ Fabrication introuvable")
                    continue
                js = job.get("status")
                if js in ACTIVE_JOB_STATUSES:
                    busy = True
                    if t["status"] == "running":
                        t["progress"] = int(job.get("progress") or 0)
                        t["step"] = ("⏸️ En pause : quota Claude atteint, reprise automatique dès qu'il revient"
                                     if js == "paused_quota" else (job.get("step") or "En cours"))
                elif js == "done":
                    if t["status"] == "running":
                        t["session_id"] = job.get("session_id") or ""
                        t["progress"] = 100
                        if t.get("publish_platforms"):
                            t["status"] = "waiting_validation"
                            t["step"] = "Vidéo prête : regarde-la et valide-la pour qu'elle soit programmée"
                        else:
                            t["status"] = "done"
                            t["step"] = "Vidéo prête dans Mes vidéos"
                    else:
                        t["status"] = "cancelled_done"
                elif js == "error":
                    if t["status"] == "running":
                        err = job.get("error") or "Erreur inconnue"
                        t.update(status="error", error=err, step=f"❌ {err}"[:300])
                    else:
                        t["status"] = "cancelled_done"

            # 2. Programmer les vidéos validées (et seulement elles)
            for t in tasks:
                if t.get("status") != "waiting_validation":
                    continue
                meta = cls._render_meta(t.get("session_id") or "")
                if meta is None:
                    t.update(status="error", error="Vidéo supprimée avant validation", step="Vidéo supprimée")
                    continue
                if not meta.get("validated"):
                    continue
                when = next_free_slot(t.get("publish_at") or "", now)
                try:
                    t["post_id"] = scheduler(t, meta, when) or ""
                    t["publish_at"] = when
                    t["status"] = "scheduled"
                    t["step"] = f"Programmée le {when.replace('T', ' à ')}"
                except Exception as e:
                    t["step"] = f"Programmation impossible : {e}"[:300]

            # 3. Lancer la suivante (une seule fabrication à la fois)
            if not busy:
                for t in tasks:
                    if t.get("status") != "pending":
                        continue
                    sa = t.get("start_at")
                    if sa:
                        try:
                            if datetime.fromisoformat(sa) > now:
                                continue
                        except ValueError:
                            pass
                    if launcher is None:
                        break
                    try:
                        t["job_id"] = launcher(t)
                        t.update(status="running", progress=5, step="Fabrication lancée")
                        busy = True
                    except Exception as e:
                        t.update(status="error", error=str(e), step=f"❌ {e}"[:300])
                        continue
                    break
            waiting = any(t.get("status") == "pending" for t in tasks)
            return busy, waiting

        busy, waiting = cls._mutate(_fn)
        keep_awake = busy or waiting
        cls._set_awake(keep_awake)

    @classmethod
    def start_worker(cls):
        from core import edition as _edition
        if _edition.is_public():
            return
        if cls._worker_started:
            return
        cls._worker_started = True
        atexit.register(cls._set_awake, False)

        def _loop():
            while not cls._stop_flag:
                try:
                    cls.tick()
                except Exception as e:
                    print(f"⚠️ Pilote auto : {e}")
                time.sleep(10)

        threading.Thread(target=_loop, daemon=True).start()
