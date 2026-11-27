"""
Débit de parole RÉEL (mots par seconde), appris vidéo après vidéo, pour que la durée livrée colle à la durée demandée.

Avant : le script était calibré à 2,65 mots/s alors que les voix réelles parlent à ~3,0-3,6 mots/s
(vidéos de 60 s livrées en 44-53 s). Ici :
- chaque voix générée enregistre son débit mesuré (mots / durée de la voix finale), par fournisseur ;
- la longueur du script (nombre de mots) est calculée avec ce débit ;
- après la voix, `fit_tempo` dit s'il faut resserrer la voix pour ne pas dépasser la durée demandée.
"""
import json
import math
import threading
import time
from typing import Dict, Optional

from config import STORAGE_DIR

RATE_FILE = STORAGE_DIR / "speech_rate.json"
_LOCK = threading.Lock()

DEFAULT_WPS = 3.0        # français parlé de Short, voix ElevenLabs à vitesse ~1,08 (point de départ avant mesure)
MIN_WPS, MAX_WPS = 2.2, 4.2
ALPHA = 0.35             # poids de la dernière mesure (moyenne glissante)
MAX_TOTAL_SPEEDUP = 1.15  # au-delà, la voix devient pressée et métallique (vitesse ElevenLabs × accélération FFmpeg)

# Vitesse ElevenLabs par défaut (paramètre voice_settings.speed, 0,7 à 1,2) : un peu plus vif que 1,0, comme les Shorts.
DEFAULT_EL_SPEED = 1.08


def provider_family(provider: str) -> str:
    p = str(provider or "").lower()
    if "elevenlabs" in p:  # y compris « multi:elevenlabs+… »
        return "elevenlabs"
    for k in ("gemini", "edge", "local_hd"):
        if k in p:
            return k
    return p or "unknown"


def _load() -> Dict[str, Dict[str, float]]:
    try:
        d = json.loads(RATE_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _clamp(x: float) -> float:
    return max(MIN_WPS, min(MAX_WPS, float(x)))


def words_per_sec(provider: Optional[str] = None) -> float:
    """Débit appris pour ce fournisseur de voix ; sinon le dernier débit appris toutes voix confondues ; sinon 3,0."""
    data = _load()
    if provider:
        e = data.get(provider_family(provider))
        if isinstance(e, dict) and e.get("n"):
            return _clamp(e.get("wps", DEFAULT_WPS))
    e = data.get("_all")
    if isinstance(e, dict) and e.get("n"):
        return _clamp(e.get("wps", DEFAULT_WPS))
    return DEFAULT_WPS


def record(provider: str, words: int, duration_s: float) -> Optional[float]:
    """Enregistre une mesure (voix finale, après accélération éventuelle). Ignore les mesures aberrantes."""
    try:
        words, duration_s = int(words), float(duration_s)
    except (TypeError, ValueError):
        return None
    if words < 15 or duration_s < 5:
        return None
    wps = words / duration_s
    if not (1.2 <= wps <= 6.0):
        return None
    fam = provider_family(provider)
    with _LOCK:
        data = _load()
        for key in (fam, "_all"):
            e = data.get(key) if isinstance(data.get(key), dict) else {}
            n = int(e.get("n") or 0)
            old = float(e.get("wps") or wps)
            new = wps if n == 0 else (1 - ALPHA) * old + ALPHA * wps
            data[key] = {"wps": round(_clamp(new), 3), "n": n + 1, "last": round(wps, 3), "at": int(time.time())}
        try:
            RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            RATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass
    return round(wps, 3)


def fit_tempo(voice_duration_s: float, target_s: float, already_speedup: float = 1.0, tolerance: float = 0.06) -> float:
    """
    Accélération supplémentaire (≥ 1.0) à appliquer à la voix pour ne pas dépasser la durée demandée de plus de
    `tolerance`. Plafonnée pour que vitesse ElevenLabs × accélérations ≤ MAX_TOTAL_SPEEDUP. 1.0 = ne rien faire.
    Une voix trop COURTE n'est jamais ralentie (une voix ralentie sonne faux) : c'est le script qu'on rallonge
    la fois suivante, grâce au débit appris.
    """
    try:
        dur, tgt, done = float(voice_duration_s), float(target_s), max(0.5, float(already_speedup or 1.0))
    except (TypeError, ValueError):
        return 1.0
    if dur <= 0 or tgt <= 0 or dur <= tgt * (1 + tolerance):
        return 1.0
    need = dur / (tgt * (1 + tolerance / 2))
    room = MAX_TOTAL_SPEEDUP / done
    t = math.floor(min(need, room) * 1000) / 1000.0  # arrondi par défaut : jamais au-dessus du plafond
    return t if t > 1.01 else 1.0


def cap_style_tempo(style_tempo: float, el_speed: float = 1.0) -> float:
    """Accélération d'un style (ex. Stickman ×1,12) ramenée pour que vitesse ElevenLabs × tempo ≤ MAX_TOTAL_SPEEDUP."""
    try:
        st, sp = float(style_tempo or 1.0), max(0.5, float(el_speed or 1.0))
    except (TypeError, ValueError):
        return 1.0
    if st <= 1.0:
        return st
    return round(max(1.0, min(st, MAX_TOTAL_SPEEDUP / sp)), 3)
