"""
Barre de progression qui avance pendant les longues étapes (rendu, montage, IA) au lieu de rester figée.

- `MonotoneProgress` : enveloppe le rappel de progression ; le pourcentage ne recule jamais et l'heure
  de la dernière mise à jour est connue.
- `ticking(...)` : pendant un bloc `with`, fait avancer doucement la barre de `start` vers `end`
  (courbe qui ralentit, jamais `end` atteint) et affiche le temps écoulé, sauf si l'étape envoie
  elle-même des nouvelles récentes (ex. numéro d'image Blender).
"""
import math
import threading
import time
from contextlib import contextmanager
from typing import Callable, Optional


def _fmt_elapsed(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec} s"
    m, s = divmod(sec, 60)
    return f"{m} min {s:02d} s"


class MonotoneProgress:
    def __init__(self, cb: Optional[Callable[[int, str], None]] = None):
        self.cb = cb
        self.pct = 0
        self.msg = ""
        self.last_update = time.time()
        self._lock = threading.Lock()

    def __call__(self, pct: int, msg: str) -> None:
        with self._lock:
            self.pct = max(self.pct, int(pct))
            self.msg = msg
            self.last_update = time.time()
            pct_out = self.pct
        if self.cb:
            try:
                self.cb(pct_out, msg)
            except Exception:
                pass

    def tick(self, pct: int, msg: str) -> None:
        """Mise à jour du minuteur : n'efface pas une nouvelle plus fraîche venue de l'étape elle-même."""
        with self._lock:
            self.pct = max(self.pct, int(pct))
            pct_out = self.pct
        if self.cb:
            try:
                self.cb(pct_out, msg)
            except Exception:
                pass


def eased(start: int, end: int, elapsed: float, est_sec: float) -> int:
    """Pourcentage qui tend vers `end - 1` : ~63 % du chemin à `est_sec`, ~86 % au double."""
    est = max(1.0, float(est_sec or 1.0))
    frac = 1.0 - math.exp(-max(0.0, elapsed) / est)
    return min(end - 1, start + int((end - start) * frac)) if end > start else start


@contextmanager
def ticking(progress, start: int, end: int, est_sec: float, msg: str, every: float = 3.0, quiet_after: float = 6.0):
    """
    `progress` : un `MonotoneProgress` (ou une simple fonction (pct, msg), alors enveloppée).
    Le minuteur se tait tant que l'étape a donné des nouvelles il y a moins de `quiet_after` secondes.
    """
    prog = progress if isinstance(progress, MonotoneProgress) else MonotoneProgress(progress)
    prog(start, msg)
    stop = threading.Event()
    t0 = time.time()

    def _run():
        while not stop.wait(every):
            if time.time() - prog.last_update < quiet_after and prog.msg != msg:
                continue  # l'étape vient de donner ses propres nouvelles
            el = time.time() - t0
            prog.tick(eased(start, end, el, est_sec), f"{msg} · {_fmt_elapsed(el)}")

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    try:
        yield prog
    finally:
        stop.set()
