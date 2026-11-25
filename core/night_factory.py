import atexit
import json
import os
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from config import STORAGE_DIR, DEFAULT_THEME, DEFAULT_SUBTITLE_STYLE
from core.pipeline import ShortCrewPipeline
from core.gemini_studio import GeminiStudio
from core.social_publisher import FreeSocialPublisher

NIGHT_QUEUE_FILE = STORAGE_DIR / "night_factory.json"
_LOCK = threading.Lock()


class NightFactory:
    """
    'Mode Nuit / Usine Automatique' — Crée tes vidéos pendant que tu dors !
    - Empêche le Mac de se mettre en veille via `caffeinate -i` pendant le lot
    - Exécute une liste de sujets (standard ou avec un Plugin de Style DA) à l'heure choisie
    - Peut programmer automatiquement chaque vidéo générée dans Pulse
    """

    _worker_started = False
    _stop_flag = False
    _caffeinate_proc: Optional[subprocess.Popen] = None

    @classmethod
    def load_tasks(cls) -> List[Dict[str, Any]]:
        with _LOCK:
            if not NIGHT_QUEUE_FILE.exists():
                return []
            try:
                with open(NIGHT_QUEUE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
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
    def enqueue_batch(
        cls,
        topics: List[str],
        plugin_id: Optional[str] = None,
        target_duration_sec: int = 60,
        engine: str = "claude",
        model: Optional[str] = None,
        start_at: str = "",
        theme: str = DEFAULT_THEME,
        subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
        voice: Optional[str] = None,
        keep_awake: bool = True,
        auto_publish_platforms: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        tasks = cls.load_tasks()
        created = []
        for raw_topic in topics:
            t = raw_topic.strip()
            if not t:
                continue
            item = {
                "id": f"night_{uuid.uuid4().hex[:8]}",
                "topic": t,
                "plugin_id": (plugin_id or "").strip(),
                "target_duration_sec": max(15, min(180, int(target_duration_sec or 60))),
                "engine": (engine or "claude").strip().lower(),
                "model": (model or "").strip(),
                "start_at": start_at.strip(),
                "theme": theme,
                "subtitle_style": subtitle_style,
                "voice": voice or "",
                "keep_awake": keep_awake,
                "auto_publish_platforms": auto_publish_platforms or [],
                "status": "pending",
                "progress": 0,
                "step": "En attente (Mode Nuit)...",
                "session_id": "",
                "error": "",
                "created_at": time.strftime("%Y-%m-%d %H:%M"),
            }
            tasks.append(item)
            created.append(item)
        cls.save_tasks(tasks)
        cls.start_worker()
        return created

    @classmethod
    def clear_completed(cls):
        tasks = [t for t in cls.load_tasks() if t.get("status") in ("pending", "running")]
        cls.save_tasks(tasks)

    @classmethod
    def cancel_task(cls, task_id: str):
        tasks = [t for t in cls.load_tasks() if t.get("id") != task_id]
        cls.save_tasks(tasks)

    @classmethod
    def _set_awake(cls, active: bool):
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

    @classmethod
    def _update_task(cls, task_id: str, **kwargs):
        tasks = cls.load_tasks()
        for t in tasks:
            if t.get("id") == task_id:
                t.update(kwargs)
                break
        cls.save_tasks(tasks)

    @classmethod
    def start_worker(cls):
        if cls._worker_started:
            return
        cls._worker_started = True
        atexit.register(cls._set_awake, False)

        # Recover any stale 'running' tasks interrupted by a previous server restart
        stale = cls.load_tasks()
        recovered = False
        for t in stale:
            if t.get("status") == "running":
                t["status"] = "pending"
                t["step"] = "Reprise après redémarrage..."
                recovered = True
        if recovered:
            cls.save_tasks(stale)

        def _loop():
            while not cls._stop_flag:
                try:
                    now = datetime.now()
                    tasks = cls.load_tasks()
                    next_task = None
                    for t in tasks:
                        if t.get("status") != "pending":
                            continue
                        sa = t.get("start_at")
                        if sa:
                            try:
                                if datetime.fromisoformat(sa) > now:
                                    continue
                            except Exception:
                                pass
                        next_task = t
                        break

                    if next_task:
                        if next_task.get("keep_awake", True):
                            cls._set_awake(True)
                        tid = next_task["id"]
                        cls._update_task(tid, status="running", progress=5, step="🌙 Démarrage Mode Nuit...")
                        try:
                            if next_task.get("engine") == "gemini":
                                res = GeminiStudio.create_short(
                                    topic=next_task["topic"],
                                    plugin_id=next_task.get("plugin_id") or None,
                                    target_duration_sec=int(next_task.get("target_duration_sec") or 60),
                                    model=next_task.get("model") or None,
                                    theme=next_task.get("theme", DEFAULT_THEME),
                                    subtitle_style=next_task.get("subtitle_style", DEFAULT_SUBTITLE_STYLE),
                                    voice=next_task.get("voice") or None,
                                    progress_cb=lambda p, m, _tid=tid: cls._update_task(_tid, progress=p, step=m),
                                )
                            else:
                                res = ShortCrewPipeline.create_direct_short(
                                    topic=next_task["topic"],
                                    plugin_id=next_task.get("plugin_id") or None,
                                    target_duration_sec=int(next_task.get("target_duration_sec") or 60),
                                    theme=next_task.get("theme", DEFAULT_THEME),
                                    subtitle_style=next_task.get("subtitle_style", DEFAULT_SUBTITLE_STYLE),
                                    voice=next_task.get("voice") or None,
                                    progress_cb=lambda p, m, _tid=tid: cls._update_task(_tid, progress=p, step=m),
                                )

                            # Optional auto-publish / queue into Free Postiz
                            plats = next_task.get("auto_publish_platforms") or []
                            if plats:
                                FreeSocialPublisher.create_post(
                                    render_id=res["session_id"],
                                    video_path=res["video_path"],
                                    title=res.get("script", {}).get("title", next_task["topic"]),
                                    caption=res.get("social_caption", ""),
                                    platforms=plats,
                                    publish_now=True,
                                )

                            cls._update_task(
                                tid,
                                status="done",
                                progress=100,
                                step="✅ Vidéo fabriquée cette nuit !",
                                session_id=res["session_id"],
                            )
                        except Exception as e:
                            cls._update_task(tid, status="error", error=str(e), step=f"❌ Erreur : {e}")
                    else:
                        cls._set_awake(False)
                except Exception:
                    pass
                time.sleep(10)

        threading.Thread(target=_loop, daemon=True).start()
