"""
Casting des voix ElevenLabs : l'IA choisit, d'après le script et le style, la voix du narrateur et celle de chaque
personnage, avec des réglages adaptés (stabilité, style, vitesse).

Voix proposées à l'IA, dans cet ordre :
0. les voix VALIDÉES par l'utilisateur, chacune avec ses emplois (narrateur d'histoire, explication, enfant…) :
   elles passent avant tout, mais seulement pour l'emploi qui leur correspond (jamais une voix unique pour tout) ;
1. les voix de l'utilisateur (clonées ou créées par lui) ;
2. les voix de la bibliothèque ElevenLabs les plus utilisées dans la langue du script (cache 7 jours) ;
3. les voix par défaut d'ElevenLabs (anglophones : elles gardent un accent en français, donc en dernier recours).
Une voix de la bibliothèque est ajoutée au compte au moment de l'utiliser (une seule fois, mémorisée).
"""
import json
import re
import threading
import time
from typing import Any, Dict, List, Optional

import requests

from config import STORAGE_DIR

API = "https://api.elevenlabs.io/v1"
LIBRARY_CACHE = STORAGE_DIR / "el_voice_library.json"
ADDED_FILE = STORAGE_DIR / "el_voice_added.json"
CACHE_TTL_SEC = 7 * 86400
_LOCK = threading.Lock()

# Voix par défaut d'ElevenLabs (présentes sur tous les comptes). use = usages où elles sonnent bien.
DEFAULT_VOICES: List[Dict[str, str]] = [
    {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George", "gender": "male", "age": "middle_aged", "accent": "british", "use": "narration, conte, documentaire", "descriptive": "chaleureux, posé"},
    {"voice_id": "nPczCjzI2devNBz1zQrb", "name": "Brian", "gender": "male", "age": "middle_aged", "accent": "american", "use": "narration, mystère, voix off grave", "descriptive": "grave, profond"},
    {"voice_id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel", "gender": "male", "age": "middle_aged", "accent": "british", "use": "info, explication, présentateur", "descriptive": "autoritaire, net"},
    {"voice_id": "pqHfZKP75CVOKJDWnPLe", "name": "Bill", "gender": "male", "age": "old", "accent": "american", "use": "grand-père, documentaire, sagesse", "descriptive": "âgé, rassurant"},
    {"voice_id": "N2lVS1w4EtoT3dr4eOWO", "name": "Callum", "gender": "male", "age": "middle_aged", "accent": "transatlantic", "use": "méchant, suspense, personnage rugueux", "descriptive": "rauque, intense"},
    {"voice_id": "TX3LPaxmHKxFdv7VOQHJ", "name": "Liam", "gender": "male", "age": "young", "accent": "american", "use": "ado, réseaux sociaux, énergie", "descriptive": "jeune, énergique"},
    {"voice_id": "bIHbv24MWmeRgasZH58o", "name": "Will", "gender": "male", "age": "young", "accent": "american", "use": "conversation, humour, pote", "descriptive": "décontracté, amical"},
    {"voice_id": "cjVigY5qzO86Huf0OWal", "name": "Eric", "gender": "male", "age": "middle_aged", "accent": "american", "use": "pub, présentation produit", "descriptive": "doux, fiable"},
    {"voice_id": "IKne3meq5aSn9XLyUdCD", "name": "Charlie", "gender": "male", "age": "young", "accent": "australian", "use": "conversation, sketch", "descriptive": "naturel, joyeux"},
    {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah", "gender": "female", "age": "young", "accent": "american", "use": "narration douce, info", "descriptive": "douce, rassurante"},
    {"voice_id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda", "gender": "female", "age": "middle_aged", "accent": "american", "use": "conte pour enfants, tuto, chaleur", "descriptive": "chaleureuse, souriante"},
    {"voice_id": "pFZP5JQG7iQjIQuC4Bku", "name": "Lily", "gender": "female", "age": "middle_aged", "accent": "british", "use": "narration, émotion, histoire vraie", "descriptive": "veloutée, chaleureuse"},
    {"voice_id": "Xb7hH8MSUJpSbSDYk0k2", "name": "Alice", "gender": "female", "age": "middle_aged", "accent": "british", "use": "explication, formation", "descriptive": "claire, assurée"},
    {"voice_id": "FGY2WhTYpPnrIDTdsKH5", "name": "Laura", "gender": "female", "age": "young", "accent": "american", "use": "réseaux sociaux, enthousiasme", "descriptive": "pétillante"},
    {"voice_id": "cgSgspJ2msm6clMCkdW9", "name": "Jessica", "gender": "female", "age": "young", "accent": "american", "use": "personnage drôle, ado, sketch", "descriptive": "expressive, espiègle"},
]

# Usages de la bibliothèque interrogés (un appel chacun, puis cache 7 jours)
LIBRARY_USE_CASES = ("narrative_story", "characters_animation", "social_media", "informative_educational", "conversational")

# Emplois d'une voix validée par l'utilisateur (réglage elevenlabs.voice_roster)
ROLES: Dict[str, str] = {
    "narrateur_recit": "narrateur d'histoire, conte, mystère, drame",
    "narrateur_energique": "narrateur énergique : humour, réseaux sociaux, liste, top",
    "explication": "explication, tuto, info (posé et clair)",
    "narratrice": "narratrice (voix de femme)",
    "enfant_ado": "enfant ou ado",
    "personnage_comique": "personnage drôle, sketch",
    "mechant": "méchant, voix inquiétante",
    "personne_agee": "personne âgée",
}
ACCENTS_NATIVE = {"fr": ("parisian", "standard", "french", "france", "")}
FOREIGN_NAME_HINTS = ("american", "british", "australian", "english", "us ", "uk ")
RECENT_NARRATORS_LIMIT = 3


def load_roster() -> List[Dict[str, Any]]:
    """Voix validées à l'oreille par l'utilisateur : [{voice_id, name, roles: [...], note}]."""
    try:
        from core.settings_store import load_settings
        raw = (load_settings().get("elevenlabs") or {}).get("voice_roster") or []
    except Exception:
        raw = []
    out = []
    for v in raw if isinstance(raw, list) else []:
        if not isinstance(v, dict) or not str(v.get("voice_id") or "").strip():
            continue
        roles = [r for r in (v.get("roles") or []) if r in ROLES]
        out.append({"voice_id": str(v["voice_id"]).strip()[:64], "name": str(v.get("name") or "")[:40],
                    "roles": roles, "note": str(v.get("note") or "")[:120]})
    return out


def sanitize_roster(items: Any) -> List[Dict[str, Any]]:
    """Nettoie une liste envoyée par l'interface avant de l'enregistrer."""
    out, seen = [], set()
    for v in items if isinstance(items, list) else []:
        if not isinstance(v, dict):
            continue
        vid = re.sub(r"[^A-Za-z0-9]", "", str(v.get("voice_id") or ""))[:64]
        roles = [r for r in (v.get("roles") or []) if r in ROLES]
        if not vid or not roles or vid in seen:
            continue
        seen.add(vid)
        out.append({"voice_id": vid, "name": str(v.get("name") or "")[:40], "roles": roles, "note": str(v.get("note") or "")[:120]})
    return out[:30]


def recent_narrators(limit: int = RECENT_NARRATORS_LIMIT) -> List[str]:
    """Noms des voix de narrateur des dernières vidéos (pour varier d'une vidéo à l'autre)."""
    try:
        from config import RENDERS_DIR
        metas = sorted(RENDERS_DIR.glob("*/metadata.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return []
    names: List[str] = []
    for mf in metas[: limit * 3]:
        try:
            vc = json.loads(mf.read_text(encoding="utf-8")).get("voice_casting") or {}
            n = str((vc.get("narrator") or {}).get("name") or "").strip()
        except Exception:
            continue
        if n:
            names.append(n)
        if len(names) >= limit:
            break
    return names


def _accent_score(v: Dict[str, Any], language: str) -> float:
    """+ pour un accent natif de la langue, − pour une voix étrangère (ex. « Adam – American » en français)."""
    if language not in ACCENTS_NATIVE:
        return 0.0
    acc = str(v.get("accent") or "").lower().strip()
    name = " " + str(v.get("name") or "").lower() + " "
    if any(h in name for h in FOREIGN_NAME_HINTS) or acc in ("american", "british", "australian", "transatlantic"):
        return -6.0
    if acc in ACCENTS_NATIVE[language]:
        return 2.0
    return -1.0  # québécois, belge, africain… : bien, mais pas le choix par défaut d'un public français


CAST_SYSTEM = (
    "Tu es directeur de casting voix pour des vidéos courtes. Tu choisis dans une liste fermée la voix de chaque rôle "
    "et ses réglages ElevenLabs. Tu réponds UNIQUEMENT par un objet JSON."
)

_FR_WORDS = (" le ", " la ", " les ", " des ", " est ", " une ", " et ", " je ", " tu ", " pas ", " que ", " qui ", " dans ", " pour ", " avec ", " mais ")
_EN_WORDS = (" the ", " and ", " is ", " you ", " are ", " was ", " with ", " that ", " this ", " for ", " not ", " but ", " what ", " have ")


def detect_language(text: str) -> str:
    low = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    fr = sum(low.count(w) for w in _FR_WORDS)
    en = sum(low.count(w) for w in _EN_WORDS)
    return "en" if en > fr * 1.3 else "fr"


def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path, data) -> None:
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def account_voices(key: str) -> List[Dict[str, Any]]:
    """Voix déjà présentes sur le compte ElevenLabs de l'utilisateur."""
    try:
        res = requests.get(f"{API}/voices", headers={"xi-api-key": key}, timeout=12)
        if res.status_code != 200:
            return []
        out = []
        for v in res.json().get("voices", []):
            lab = v.get("labels") or {}
            out.append({
                "voice_id": v.get("voice_id") or "",
                "name": v.get("name") or "",
                "gender": str(lab.get("gender") or ""),
                "age": str(lab.get("age") or ""),
                "accent": str(lab.get("accent") or ""),
                "language": str(lab.get("language") or ""),
                "use": str(lab.get("use_case") or lab.get("use case") or ""),
                "descriptive": str(lab.get("descriptive") or lab.get("description") or ""),
                "description": str(v.get("description") or "")[:120],
                "category": v.get("category") or "premade",
                "source": "account",
            })
        return [v for v in out if v["voice_id"]]
    except Exception:
        return []


LIBRARY_BLOCK_SEC = 3 * 86400


def library_blocked() -> bool:
    """Vrai si l'API a refusé récemment d'ajouter une voix de la bibliothèque (compte gratuit, quota de voix…)."""
    cache = _read_json(LIBRARY_CACHE, {})
    return isinstance(cache, dict) and time.time() - float(cache.get("_blocked_at") or 0) < LIBRARY_BLOCK_SEC


def _mark_library_blocked(reason: str) -> None:
    with _LOCK:
        cache = _read_json(LIBRARY_CACHE, {})
        cache = cache if isinstance(cache, dict) else {}
        cache["_blocked_at"] = time.time()
        cache["_blocked_reason"] = reason[:200]
        _write_json(LIBRARY_CACHE, cache)


def library_voices(key: str, language: str, free_only: bool = False) -> List[Dict[str, Any]]:
    """Voix de la bibliothèque ElevenLabs dans la langue, accent natif d'abord (cache 7 jours)."""
    if library_blocked():
        return []
    lang = (language or "fr")[:5]
    with _LOCK:
        cache = _read_json(LIBRARY_CACHE, {})
        entry = cache.get(lang) if isinstance(cache, dict) else None
        if isinstance(entry, dict) and entry.get("v") == 2 and time.time() - float(entry.get("at") or 0) < CACHE_TTL_SEC and entry.get("voices"):
            voices = entry["voices"]
            return [v for v in voices if v.get("free_users_allowed") or not free_only]
    found: Dict[str, Dict[str, Any]] = {}
    for uc in LIBRARY_USE_CASES:
        try:
            res = requests.get(
                f"{API}/shared-voices",
                headers={"xi-api-key": key},
                params={"page_size": 20, "language": lang, "use_cases": uc, "sort": "usage_character_count_1y"},
                timeout=12,
            )
            if res.status_code != 200:
                continue
            for v in res.json().get("voices", []):
                vid = v.get("voice_id")
                if not vid or vid in found or v.get("fiat_rate") or v.get("live_moderation_enabled"):
                    continue  # tarif spécial ou modération en direct : exclues
                found[vid] = {
                    "voice_id": vid,
                    "public_owner_id": v.get("public_owner_id") or "",
                    "name": str(v.get("name") or "")[:40],
                    "gender": str(v.get("gender") or ""),
                    "age": str(v.get("age") or ""),
                    "accent": str(v.get("accent") or ""),
                    "language": str(v.get("language") or lang),
                    "use": str(v.get("use_case") or uc),
                    "descriptive": str(v.get("descriptive") or ""),
                    "description": re.sub(r"\s+", " ", str(v.get("description") or ""))[:140],
                    "usage": int(v.get("usage_character_count_1y") or 0),
                    "free_users_allowed": bool(v.get("free_users_allowed")),
                    "is_added_by_user": bool(v.get("is_added_by_user")),
                    "source": "library",
                }
        except Exception:
            continue
    # Popularité ≠ bonne voix : on classe d'abord par accent natif, puis par usage, et on retire les doublons de nom
    ranked = sorted(found.values(), key=lambda x: (-_accent_score(x, lang[:2]), -x["usage"]))
    voices, names = [], set()
    for v in ranked:
        key = re.sub(r"\s+", " ", v["name"].split("-")[0].strip().lower())
        if key in names:
            continue
        names.add(key)
        voices.append(v)
    voices = voices[:40]
    if voices:
        with _LOCK:
            cache = _read_json(LIBRARY_CACHE, {})
            if not isinstance(cache, dict):
                cache = {}
            cache[lang] = {"at": time.time(), "voices": voices, "v": 2}
            _write_json(LIBRARY_CACHE, cache)
    return [v for v in voices if v.get("free_users_allowed") or not free_only]


def library_add_allowed() -> bool:
    """Ajouter une voix de la bibliothèque au compte ElevenLabs de l'utilisateur : seulement s'il l'a autorisé
    (réglage elevenlabs.add_library_voices). Par défaut, ClipRoll ne touche pas à son compte."""
    try:
        from core.settings_store import load_settings
        return (load_settings().get("elevenlabs") or {}).get("add_library_voices") is True
    except Exception:
        return False


def _added_ids() -> set:
    added = _read_json(ADDED_FILE, {})
    if not isinstance(added, dict):
        return set()
    return set(added.keys()) | set(str(v) for v in added.values())


def build_candidates(key: str, language: str, free_only: bool = False) -> List[Dict[str, Any]]:
    """Voix utilisables. Bibliothèque : seulement si le compte est payant (l'API refuse ces voix aux comptes
    gratuits, même ajoutées) ET si la voix est déjà sur le compte ou que l'utilisateur autorise l'ajout."""
    added_ids = _added_ids()
    allow_add = library_add_allowed()

    def _usable(v: Dict[str, Any]) -> bool:
        from_lib = v.get("source") == "library" or v.get("voice_id") in added_ids
        if not from_lib:
            return True
        if free_only:
            return False
        return allow_add or bool(v.get("is_added_by_user")) or v.get("voice_id") in added_ids

    acc = account_voices(key)
    by_id = {v["voice_id"]: v for v in acc}
    lib = library_voices(key, language, free_only=free_only)
    lib_by_id = {v["voice_id"]: v for v in lib}
    roster = []
    for r in load_roster():
        # voix validée pas encore ajoutée au compte : si elle vient de la bibliothèque, elle sera ajoutée au 1er usage
        base = dict(by_id.get(r["voice_id"]) or lib_by_id.get(r["voice_id"])
                    or {"voice_id": r["voice_id"], "name": r["name"], "source": "account"})
        base.update({"roles": r["roles"], "validated": True, "note": r.get("note", "")})
        base["name"] = base.get("name") or r["name"]
        roster.append(base)
    own = [v for v in acc if v.get("category") in ("cloned", "professional", "generated")]
    premade = [v for v in acc if v.get("category") == "premade"]
    seen = set()
    out: List[Dict[str, Any]] = []
    for group in (roster, own[:8], lib, premade, DEFAULT_VOICES):
        for v in group:
            vid = v.get("voice_id")
            if vid and vid not in seen and _usable(v):
                seen.add(vid)
                out.append(dict({"source": "default", "language": "en"}, **v))
    for i, v in enumerate(out):
        v["ref"] = f"V{i + 1}"
    return out


def _describe(v: Dict[str, Any]) -> str:
    bits = [v["ref"], v.get("name", "")]
    who = ", ".join(x for x in (v.get("gender"), v.get("age")) if x)
    if who:
        bits.append(who)
    for k in ("language", "accent", "use", "descriptive"):
        if v.get(k):
            bits.append(f"{k}: {v[k]}")
    if v.get("description"):
        bits.append(v["description"])
    src = {"account": "voix du compte", "library": "bibliothèque", "default": "voix par défaut (anglophone)"}.get(v.get("source"), "")
    if v.get("category") in ("cloned", "professional"):
        src = "voix clonée de l'utilisateur"
    if v.get("validated"):
        src = "★ VALIDÉE par l'utilisateur pour : " + ", ".join(ROLES[r] for r in v.get("roles") or [] if r in ROLES)
        if v.get("note"):
            src += f" ({v['note']})"
    bits.append(src)
    return " · ".join(b for b in bits if b)


def _clamp(x, lo, hi, default):
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return default


def _default_speed() -> float:
    try:
        from core.speech_rate import DEFAULT_EL_SPEED
        from core.settings_store import load_settings
        return max(0.95, min(1.15, float((load_settings().get("elevenlabs") or {}).get("speed") or DEFAULT_EL_SPEED)))
    except Exception:
        return 1.08


def _settings(d: Dict[str, Any]) -> Dict[str, float]:
    d = d if isinstance(d, dict) else {}
    return {
        "stability": _clamp(d.get("stability"), 0.25, 0.8, 0.45),
        "similarity_boost": _clamp(d.get("similarity_boost"), 0.6, 0.9, 0.78),
        "style": _clamp(d.get("style"), 0.0, 0.6, 0.25),
        "speed": _clamp(d.get("speed"), 0.95, 1.15, _default_speed()),
    }


def ai_cast(script_text: str, speakers: List[Dict[str, str]], style_hint: str, language: str,
            cands: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Demande à Claude le casting ; renvoie {"narrator": {...}, "characters": {nom: {...}}} avec des refs valides."""
    from core.claude_bridge import ClaudeBridge
    refs = {v["ref"]: v for v in cands}
    recent = recent_narrators()
    roles = "\n".join(f"- {s['name']}" + (f" ({s['hint']})" if s.get("hint") else "") for s in speakers) or "- (narrateur seul)"
    prompt = (
        f"Langue du script : {language}\n"
        f"Style de la vidéo : {style_hint or 'non précisé'}\n\n"
        f"Rôles qui parlent :\n{roles}\n\n"
        f"Script (extrait) :\n{(script_text or '')[:2600]}\n\n"
        f"Voix disponibles (choisis uniquement parmi ces références) :\n" + "\n".join(_describe(v) for v in cands[:60]) + "\n\n"
        + (f"Voix de narrateur des dernières vidéos : {', '.join(recent)}. Si une autre voix convient aussi bien, prends-la "
           "pour que la chaîne ne sonne pas toujours pareil.\n\n" if recent else "")
        + "Règles de casting :\n"
        "- D'abord le GENRE du script (histoire/conte/mystère, humour, tuto/explication, pub, témoignage…), puis l'emploi de chaque rôle.\n"
        "- Les voix ★ VALIDÉES sont les meilleures de l'utilisateur, mais SEULEMENT pour les emplois indiqués : une voix validée "
        "« narrateur d'histoire » ne fait pas un tuto ni un sketch. Si aucune voix validée ne correspond à l'emploi, prends la "
        "meilleure autre voix.\n"
        "- Priorité aux voix natives de la langue du script avec l'accent standard (une voix anglophone en français garde un accent : dernier recours).\n"
        "- Âge et genre cohérents avec le rôle ; un enfant ou un ado a une voix jeune.\n"
        "- Le narrateur porte la vidéo : voix captivante qui colle au ton (grave et lente pour le mystère, vive pour l'humour ou "
        "les réseaux sociaux, claire et posée pour une explication, chaleureuse pour une histoire tendre).\n"
        "- Récit à la 1re personne : le narrateur EST le personnage principal, donne-lui la même voix.\n"
        "- Deux personnages différents n'ont jamais la même voix.\n"
        "- Réglages : stability 0.30 à 0.45 pour une voix expressive (histoire, humour, peur), 0.50 à 0.65 pour une voix posée "
        "(tuto, info) ; style 0.0 à 0.45 (plus haut = artefacts) ; speed 1.0 à 1.12 (Shorts : 1.08 par défaut, vif = 1.08 à 1.12, "
        "posé ou émouvant = 1.0 à 1.05).\n\n"
        'Réponds en JSON : {"narrator": {"voice": "V3", "stability": 0.4, "style": 0.3, "speed": 1.05, "why": "5 mots"}, '
        '"characters": {"NomExact": {"voice": "V7", "stability": 0.4, "style": 0.3, "speed": 1.0, "why": "5 mots"}}}'
    )
    try:
        raw = ClaudeBridge.query(prompt, system_prompt=CAST_SYSTEM, action="voice_casting", model="sonnet")
    except Exception as e:
        print(f"Casting voix par l'IA indisponible ({e}) : choix automatique.")
        return None
    txt = (raw or "").strip()
    try:
        data = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
    except Exception:
        return None
    nar = data.get("narrator") if isinstance(data, dict) else None
    if not isinstance(nar, dict) or nar.get("voice") not in refs:
        return None
    out = {"narrator": dict(nar, voice=refs[nar["voice"]]), "characters": {}}
    for name, c in (data.get("characters") or {}).items():
        if isinstance(c, dict) and c.get("voice") in refs:
            out["characters"][str(name)] = dict(c, voice=refs[c["voice"]])
    return out


_GENRE_USES = (
    (("peur", "nuit", "mystère", "secret", "disparu", "horreur", "fantôme", "sombre"), ("narrat", "mystère", "suspense", "grave", "deep", "story")),
    (("astuce", "comment", "étape", "méthode", "conseil", "explique", "tuto", "apprendre"), ("inform", "educat", "explication", "clair")),
    (("drôle", "blague", "sketch", "lol", "délire", "absurde"), ("charact", "conversation", "humour", "social")),
)
# même découpage, en emplois de voix validées (narrateur)
_GENRE_ROLES = ("narrateur_recit", "explication", "narrateur_energique")


def narrator_role(text: str) -> str:
    """Emploi de narrateur qui colle au script (repli sans IA)."""
    low = (text or "").lower()
    for (words, _), role in zip(_GENRE_USES, _GENRE_ROLES):
        if any(w in low for w in words):
            return role
    return "narrateur_recit"


def heuristic_pick(cands: List[Dict[str, Any]], language: str, text: str, female: Optional[bool] = None,
                   young: bool = False, exclude: Optional[set] = None, role: str = "") -> Optional[Dict[str, Any]]:
    """Repli sans IA : voix validée pour l'emploi, langue et accent natifs, usage qui colle au ton, genre/âge si connus."""
    low = (text or "").lower()
    wanted = ("narrat", "story", "narration")
    for words, uses in _GENRE_USES:
        if any(w in low for w in words):
            wanted = uses
            break
    best, best_score = None, -1e9
    for i, v in enumerate(cands):
        if exclude and v["voice_id"] in exclude:
            continue
        blob = " ".join(str(v.get(k) or "") for k in ("use", "descriptive", "description", "name")).lower()
        score = 0.0
        if str(v.get("language") or "").lower().startswith(language):
            score += 4
        if v.get("validated"):
            score += 10 if role and role in (v.get("roles") or []) else -2  # validée, mais pas pour cet emploi
        if v.get("source") == "default" and language != "en":
            score -= 5  # anglophone : accent en français
        score += _accent_score(v, language) * 0.5
        if v.get("category") in ("cloned", "professional"):
            score += 1
        score += sum(1.5 for w in wanted if w in blob)
        g = str(v.get("gender") or "").lower()
        if female is not None and g:
            score += 2 if (g == "female") == female else -3
        if young and "young" in str(v.get("age") or ""):
            score += 1
        score -= i * 0.01  # à égalité, l'ordre (compte, puis bibliothèque la plus utilisée) départage
        if score > best_score:
            best, best_score = v, score
    return best


def resolve_voice_id(key: str, v: Dict[str, Any]) -> str:
    """Identifiant utilisable pour la synthèse ; ajoute au compte une voix de la bibliothèque si besoin."""
    if v.get("source") != "library" or v.get("is_added_by_user"):
        return v["voice_id"]
    with _LOCK:
        added = _read_json(ADDED_FILE, {})
        if isinstance(added, dict) and added.get(v["voice_id"]):
            return added[v["voice_id"]]
    if not library_add_allowed():
        print(f"Voix « {v.get('name')} » non ajoutée : ClipRoll n'ajoute pas de voix à ton compte ElevenLabs sans ton accord.")
        return ""
    try:
        res = requests.post(
            f"{API}/voices/add/{v.get('public_owner_id')}/{v['voice_id']}",
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json={"new_name": f"ClipRoll · {v.get('name') or 'voix'}"[:60]},
            timeout=15,
        )
        if res.status_code == 200 and res.json().get("voice_id"):
            new_id = res.json()["voice_id"]
            with _LOCK:
                added = _read_json(ADDED_FILE, {})
                added = added if isinstance(added, dict) else {}
                added[v["voice_id"]] = new_id
                _write_json(ADDED_FILE, added)
            print(f"🎙️ Voix « {v.get('name')} » ajoutée à ton compte ElevenLabs.")
            return new_id
        print(f"Voix de la bibliothèque non ajoutée (HTTP {res.status_code} : {res.text[:120]}).")
        if res.status_code in (400, 401, 402, 403):
            _mark_library_blocked(f"HTTP {res.status_code} : {res.text[:150]}")
    except Exception as e:
        print(f"Voix de la bibliothèque non ajoutée ({e}).")
    return ""


def cast_voices(key: str, script_text: str, speakers: Optional[List[Dict[str, Any]]] = None, style_hint: str = "",
                free_only: bool = False) -> Optional[Dict[str, Any]]:
    """
    speakers : [{"key": clé normalisée, "name": nom affiché, "female": bool|None, "hint": "12 ans, garçon…"}]
    Renvoie {"language", "narrator": {"voice_id", "name", "settings"}, "characters": {key: {...}}} ou None.
    """
    if not key:
        return None
    language = detect_language(script_text)
    if not free_only:
        try:  # compte gratuit : seulement les voix de la bibliothèque ouvertes aux comptes gratuits
            sub = requests.get(f"{API}/user/subscription", headers={"xi-api-key": key}, timeout=8)
            free_only = sub.status_code == 200 and str(sub.json().get("tier") or "").lower() == "free"
        except Exception:
            pass
    cands = build_candidates(key, language, free_only=free_only)
    if not cands:
        return None
    speakers = [s for s in (speakers or []) if s.get("key")]
    picked = ai_cast(script_text, [{"name": s.get("name") or s["key"], "hint": s.get("hint", "")} for s in speakers],
                     style_hint, language, cands)

    def _final(v: Dict[str, Any], raw: Dict[str, Any], used: set) -> Optional[Dict[str, Any]]:
        vid = resolve_voice_id(key, v)
        if not vid:  # ajout impossible (quota de voix, compte gratuit) : meilleure voix déjà utilisable
            alt = heuristic_pick([c for c in cands if c.get("source") != "library" or c.get("is_added_by_user")],
                                 language, script_text, exclude=used, role=narrator_role(script_text))
            if not alt:
                return None
            v, vid = alt, alt["voice_id"]
        used.add(vid)
        return {"voice_id": vid, "name": v.get("name", ""), "settings": _settings(raw), "why": str(raw.get("why") or "")[:80],
                "source": "validée" if v.get("validated") else v.get("source", ""),
                "foreign": bool(language != "en" and (v.get("source") == "default" or _accent_score(v, language) <= -6))}

    used: set = set()
    result: Dict[str, Any] = {"language": language, "characters": {}}
    if picked:
        result["narrator"] = _final(picked["narrator"]["voice"], picked["narrator"], used)
        by_name = {str(k).strip().lower(): c for k, c in picked["characters"].items()}
        for s in speakers:
            c = by_name.get(str(s.get("name") or "").strip().lower()) or by_name.get(s["key"])
            if c:
                fin = _final(c["voice"], c, used)
                if fin:
                    result["characters"][s["key"]] = fin
    if not result.get("narrator"):
        v = heuristic_pick(cands, language, script_text, role=narrator_role(script_text))
        result["narrator"] = _final(v, {}, used) if v else None
    for s in speakers:
        if s["key"] not in result["characters"]:
            v = heuristic_pick(cands, language, script_text, female=s.get("female"), exclude=used)
            if v:
                fin = _final(v, {}, used)
                if fin:
                    result["characters"][s["key"]] = fin
    if not result.get("narrator"):
        return None
    summary = ", ".join([f"narrateur → {result['narrator']['name']}"] + [f"{k} → {c['name']}" for k, c in result["characters"].items()])
    print(f"🎭 Casting voix ({'IA' if picked else 'auto'}, {language}) : {summary}")
    result["by_ai"] = bool(picked)
    if result["narrator"].get("foreign"):
        result["accent_warning"] = (
            "Aucune voix française utilisable sur ce compte ElevenLabs : la voix choisie est anglophone et aura un accent. "
            + ("La bibliothèque de voix a été refusée par l'API (compte gratuit ?). " if library_blocked() else "")
            + "Ajoute une voix française à ton compte ou valide-en une dans Voix."
        )
        print("⚠️ " + result["accent_warning"])
    return result
