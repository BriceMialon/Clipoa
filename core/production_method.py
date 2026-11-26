"""
Méthode de production ClipRoll — généralisée à partir des séries qui marchent
(Docteur Shark, Horreur « Terminaison incomplète ») :

1. Les plans sont calés sur la VOIX réelle (pas sur un découpage uniforme), un plan toutes les 2 à 4 s.
2. Le twist (révélation) est repéré : silence musical juste avant, impact grave dessus.
3. Les bruitages sont des ÉVÉNEMENTS ancrés (coupe, mot, CTA) : <= 20 par vidéo, souffle seulement aux
   vrais changements de plan (écart minimum), jamais le même bruitage deux fois en moins de 4 s.
4. Sous-titres : mots-clés colorés (jaune = noms/chiffres, rouge = danger, vert = positif) + cartons
   de texte géants aux moments clés.
5. Musique d'ambiance choisie selon l'ambiance (sombre, tension, dynamique, calme), sous la voix (-17 dB,
   ducking), et une version SANS musique (voix + bruitages) livrée en plus.

Ce module ne fait que PLANIFIER (aucun appel FFmpeg/Blender) : il produit un `production_plan.json`
lisible et modifiable, consommé par SoundDesigner, BlenderEngine et VideoComposer.
Les styles (plugins) peuvent surcharger chaque réglage via `script["production"]`.
"""
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PLAN_VERSION = 1

DARK_KW = (
    "horreur", "effray", "nuit", "minuit", "dispar", "mort", "fantôme", "fantome", "sombre", "peur",
    "monstre", "seul", "glace", "triste", "miroir", "deuil", "cri", "sang", "ombre", "hurl", "cauchemar",
    "hôpital", "hopital", "silence", "instance", "terminé", "termine",
)
TENSION_KW = (
    "arnaque", "piège", "piege", "danger", "secret", "vol", "menace", "perdu", "dette", "crédit", "credit",
    "mensonge", "trahi", "confiance", "attention", "jamais", "carnet", "disparu", "faillite", "ruine",
)
UPBEAT_KW = (
    "astuce", "gagn", "réussi", "reussi", "incroyable", "drôle", "drole", "fun", "record", "top", "secret pour",
    "facile", "rapide", "génial", "genial", "hack", "bonus", "cadeau", "riche", "double",
)

RED_WORDS = {
    "peur", "peurs", "danger", "jamais", "mort", "morte", "perdu", "perdue", "vide", "piege", "arnaque", "dette",
    "dettes", "attention", "stop", "faux", "fausse", "mensonge", "voleur", "voleurs", "vole", "disparu", "disparue",
    "trop", "personne", "rien", "seul", "seule", "erreur", "pire", "pires", "ruine", "crise", "nuit", "sang",
    "terrible", "interdit", "piegee", "piege", "menace", "cri", "hurle",
}
GREEN_WORDS = {
    "gagne", "gagner", "gagnes", "double", "gratuit", "gratuite", "riche", "sauve", "sauvee", "reussi", "reussite",
    "mieux", "guerira", "gueri", "libre", "liberte", "solution", "aide", "aider", "espoir", "victoire", "gagnant",
    "facile", "pousse", "grandit", "multiplie", "economise", "epargne",
}

CTA_PATTERNS = ("abonne", "lien en bio", "mon profil", "sur mon profil", "discord", "like", "partage")

# Formules qui ouvrent une révélation (normalisées, sans espaces ni apostrophes), par priorité
STRONG_TWIST_STARTERS = ("cenetaitpas", "cenetait", "enfait", "enrealite", "saufque", "cetaitpas", "cetait", "etla", "pourtant", "soudain")

# Bruitages déclenchés par un mot prononcé (préfixe normalisé -> type de son)
WORD_SFX = (
    (("argent", "euro", "piece", "paye", "payer", "prix", "salaire", "banque", "tirelire"), "coins"),
    (("porte", "frappe", "toc", "frapper"), "knock"),
    (("grince", "ouvre", "ouvert", "ouverte", "plancher"), "creak"),
    (("coeur", "battait", "bat"), "heartbeat"),
    (("chut", "murmure", "chuchote", "secret"), "hush"),
)

# Gain appliqué à la musique générée (≈ 18 dB sous la voix après ducking, comme les séries de référence)
DEFAULT_MUSIC_DB = {"dark": -13.0, "tension": -14.0, "upbeat": -14.5, "calm": -15.0}


def norm_word(w: str) -> str:
    """minuscules, sans accents, sans ponctuation (« Pièces, » -> « pieces »)."""
    w = unicodedata.normalize("NFKD", str(w or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9€%]+", "", w)


def detect_mood(text: str) -> str:
    """Ambiance globale : 'dark' | 'tension' | 'upbeat' | 'calm'."""
    low = (text or "").lower()
    dark = sum(low.count(k) for k in DARK_KW)
    tension = sum(low.count(k) for k in TENSION_KW)
    upbeat = sum(low.count(k) for k in UPBEAT_KW)
    if dark >= 2 and dark >= tension:
        return "dark"
    if tension >= 2 and tension >= upbeat:
        return "tension"
    if upbeat >= 1:
        return "upbeat"
    if dark == 1:
        return "dark"
    return "calm"


def is_dark_mood(mood: str) -> bool:
    return mood in ("dark", "tension")


def sentence_spans(words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Découpe la liste de mots chronométrés en phrases ({i0, i1, start, end, text, n})."""
    spans: List[Dict[str, Any]] = []
    i0 = 0
    for i, w in enumerate(words):
        txt = str(w.get("word", ""))
        last = i == len(words) - 1
        gap_break = (not last) and (float(words[i + 1]["start"]) - float(w["end"]) > 0.55)
        if txt.endswith((".", "!", "?", "…", ":")) or last or gap_break:
            seg = words[i0 : i + 1]
            spans.append({
                "i0": i0,
                "i1": i,
                "start": float(seg[0]["start"]),
                "end": float(seg[-1]["end"]),
                "text": " ".join(str(x["word"]) for x in seg),
                "n": len(seg),
            })
            i0 = i + 1
    return spans


def _parse_approx(ts: str) -> Tuple[float, float]:
    """'0-3s', '3–15 s', '0:03-0:10' -> (start, end) ; (-1, -1) si illisible."""
    s = str(ts or "")
    vals: List[float] = []
    for m in re.finditer(r"(\d+):(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)", s):
        if m.group(1) is not None:
            vals.append(int(m.group(1)) * 60.0 + float(m.group(2).replace(",", ".")))
        else:
            vals.append(float(m.group(3).replace(",", ".")))
    if not vals:
        return -1.0, -1.0
    return vals[0], (vals[1] if len(vals) > 1 else -1.0)


def _find_phrase(words: List[Dict[str, Any]], phrase: str, from_idx: int = 0) -> int:
    """
    Index du mot où commence `phrase` (3 premiers mots), -1 sinon. Robuste au découpage de Whisper
    (« n'était » -> « n » + « 'était », « abonne » + « -toi ») : on compare des flux normalisés concaténés.
    """
    toks = [norm_word(t) for t in str(phrase or "").split()]
    target = "".join([t for t in toks if t][:3])
    if not target:
        return -1
    normed = [norm_word(w.get("word", "")) for w in words]
    for i in range(max(0, from_idx), len(normed)):
        if not normed[i] or not target.startswith(normed[i]):
            continue
        acc = ""
        for j in range(i, min(i + 8, len(normed))):
            acc += normed[j]
            if acc == target or (len(acc) >= len(target) and acc.startswith(target)):
                return i
            if not target.startswith(acc):
                break
    return -1


def _shot_desc(shot: Dict[str, Any]) -> str:
    if not isinstance(shot, dict):
        return ""
    return " ".join(str(shot.get(k, "")) for k in ("scene", "action", "visual") if shot.get(k)).strip()


def _snap_to_word(t: float, words: List[Dict[str, Any]], window: float = 0.6) -> float:
    best, best_d = t, window
    for w in words:
        d = abs(float(w["start"]) - t)
        if d < best_d:
            best, best_d = float(w["start"]), d
    return best


def align_shots(
    shots: Optional[List[Dict[str, Any]]],
    words: List[Dict[str, Any]],
    duration: float,
    min_len: float = 1.6,
    max_len: float = 4.2,
) -> List[Dict[str, Any]]:
    """
    Cale chaque plan du storyboard sur la voix réelle, puis impose le rythme 2-4 s :
    - ancre = texte du plan retrouvé dans la transcription, sinon start_s / timestamp_approx, sinon phrases ;
    - plans trop longs coupés aux frontières de mots, plans trop courts fusionnés.
    """
    duration = max(1.0, float(duration))
    anchors: List[Tuple[float, str]] = []
    cursor = 0
    for shot in (shots or []):
        if not isinstance(shot, dict):
            continue
        t = -1.0
        spoken = shot.get("text") or shot.get("spoken") or shot.get("line") or ""
        if spoken and words:
            idx = _find_phrase(words, spoken, cursor)
            if idx >= 0:
                t = float(words[idx]["start"])
                cursor = idx + 1
        if t < 0:
            try:
                st = float(shot.get("start_s", -1))
            except (TypeError, ValueError):
                st = -1.0
            if st >= 0:
                t = st
        if t < 0 and shot.get("timestamp_approx"):
            t = _parse_approx(shot.get("timestamp_approx"))[0]
        if 0 <= t < duration - 0.8:
            anchors.append((t, _shot_desc(shot)))

    # Ancres monotones
    clean: List[Tuple[float, str]] = []
    for t, d in sorted(anchors, key=lambda a: a[0]):
        if not clean or t - clean[-1][0] >= 0.5:
            clean.append((t, d))
    if len(clean) < 2 and words:
        clean = [(sp["start"], "") for sp in sentence_spans(words)]
    if not clean:
        clean = [(0.0, "")]
    if clean[0][0] > 0.01:
        clean[0] = (0.0, clean[0][1])

    segs: List[Dict[str, Any]] = []
    for i, (t, d) in enumerate(clean):
        end = clean[i + 1][0] if i + 1 < len(clean) else duration
        if end - t > 0.05:
            segs.append({"start": round(t, 2), "end": round(end, 2), "desc": d})

    # Découpe des plans trop longs (coupe aux débuts de mots)
    split: List[Dict[str, Any]] = []
    for s in segs:
        length = s["end"] - s["start"]
        if length <= max_len:
            split.append(s)
            continue
        n = int(math.ceil(length / 3.2))
        bounds = [s["start"]]
        for k in range(1, n):
            raw = s["start"] + k * length / n
            snapped = _snap_to_word(raw, words, 0.5) if words else raw
            if snapped - bounds[-1] >= min_len and s["end"] - snapped >= min_len:
                bounds.append(snapped)
        bounds.append(s["end"])
        for k in range(len(bounds) - 1):
            split.append({"start": round(bounds[k], 2), "end": round(bounds[k + 1], 2), "desc": s["desc"], "sub": k})

    # Fusion des plans trop courts
    merged: List[Dict[str, Any]] = []
    for s in split:
        if merged and (s["end"] - s["start"]) < min_len:
            merged[-1]["end"] = s["end"]
        else:
            merged.append(dict(s))
    if len(merged) > 1 and merged[-1]["end"] - merged[-1]["start"] < min_len:
        last = merged.pop()
        merged[-1]["end"] = last["end"]
    for i, s in enumerate(merged):
        s["index"] = i
    return merged


def find_twist_time(script: Dict[str, Any], words: List[Dict[str, Any]], duration: float) -> Optional[float]:
    """Moment de la révélation : explicite (`twist_line` / `twist_text`) sinon heuristique."""
    if not words:
        return None
    explicit = script.get("twist_text") or ""
    tl = script.get("twist_line")
    if not explicit and tl and isinstance(script.get("lines"), list):
        for ln in script["lines"]:
            if isinstance(ln, dict) and ln.get("id") == tl:
                explicit = ln.get("text", "")
    if not explicit and isinstance(tl, str) and len(tl.split()) >= 2:
        explicit = tl
    if explicit:
        idx = _find_phrase(words, explicit)
        if idx >= 0:
            return float(words[idx]["start"])

    lo, hi = duration * 0.5, duration * 0.88
    normed = [norm_word(w.get("word", "")) for w in words]
    # 1) Formules de révélation fortes (« ce n'était pas », « en fait », « sauf que »…), par priorité
    for starter in STRONG_TWIST_STARTERS:
        for i, w in enumerate(words):
            if lo <= float(w["start"]) <= hi and normed[i] and starter.startswith(normed[i]):
                if "".join(normed[i : i + 4]).startswith(starter):
                    return float(w["start"])
    # 2) phrase-choc de 2 à 5 mots dans la deuxième moitié -> la phrase suivante est le twist
    spans = sentence_spans(words)
    for k, sp in enumerate(spans):
        if lo <= sp["start"] <= hi and 2 <= sp["n"] <= 5 and k + 1 < len(spans):
            return spans[k + 1]["start"]
    # 3) premier « mais » de la deuxième moitié
    for i, w in enumerate(words):
        if lo <= float(w["start"]) <= hi and normed[i] == "mais":
            return float(w["start"])
    return None


def find_cta_times(words: List[Dict[str, Any]]) -> List[float]:
    out: List[float] = []
    normed = [norm_word(w.get("word", "")) for w in words]
    for i, n in enumerate(normed):
        tri = " ".join(normed[i : i + 3])
        if any(n.startswith(p) for p in CTA_PATTERNS if " " not in p) or any(tri.startswith(p.replace("'", "")) for p in CTA_PATTERNS if " " in p):
            t = float(words[i]["start"])
            if not out or t - out[-1] > 6.0:
                out.append(t)
    return out


def classify_keywords(script: Dict[str, Any], words: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Mots-clés à colorer : jaune (noms, chiffres, sujet), rouge (danger), vert (positif)."""
    provided = script.get("caption_keywords") if isinstance(script.get("caption_keywords"), dict) else {}
    yellow, red, green = set(), set(), set()
    for col, bucket in (("yellow", yellow), ("red", red), ("green", green)):
        for w in (provided.get(col) or []):
            n = norm_word(w)
            if n:
                bucket.add(n)

    prev_end = ""
    for i, w in enumerate(words):
        raw = str(w.get("word", "")).strip()
        n = norm_word(raw)
        if not n:
            continue
        sentence_start = i == 0 or prev_end.endswith((".", "!", "?", "…", ":"))
        if re.search(r"\d", n) or "€" in raw or "%" in raw:
            yellow.add(n)
        elif raw[:1].isupper() and not sentence_start and len(n) >= 3:
            yellow.add(n)
        elif n in RED_WORDS:
            red.add(n)
        elif n in GREEN_WORDS:
            green.add(n)
        prev_end = raw
    for t in str(script.get("hook_screen_text") or "").split():
        n = norm_word(t)
        if len(n) >= 5 and n not in red and n not in green:
            yellow.add(n)
    red -= yellow
    green -= yellow | red
    return {"yellow": sorted(yellow), "red": sorted(red), "green": sorted(green)}


def plan_sfx(
    cuts: List[float],
    words: List[Dict[str, Any]],
    twist_t: Optional[float],
    cta_times: List[float],
    duration: float,
    mood: str,
    max_events: int = 20,
    cut_min_gap: float = 10.0,
    repeat_gap: float = 4.0,
) -> List[Dict[str, Any]]:
    """Liste d'événements sonores {kind, at, db, why} respectant les règles de la méthode."""
    cand: List[Dict[str, Any]] = []
    dark = is_dark_mood(mood)
    # Priorité 0 : impact d'ouverture (le hook)
    cand.append({"kind": "impact", "at": 0.05, "db": -15.0, "why": "hook", "prio": 0})
    # Priorité 0 : le twist (silence avant, impact grave dessus)
    if twist_t is not None:
        cand.append({"kind": "drop", "at": round(twist_t, 2), "db": -11.0, "why": "twist", "prio": 0})
    # Priorité 1 : les CTA
    for t in cta_times:
        cand.append({"kind": "pop", "at": round(t + 0.3, 2), "db": -13.0, "why": "cta", "prio": 1})
    # Priorité 2 : mots déclencheurs
    for w in words:
        n = norm_word(w.get("word", ""))
        if not n:
            continue
        kind = None
        if re.search(r"\d", n) and not dark:
            kind = "ding"
        else:
            for prefixes, k in WORD_SFX:
                if any(n == p or (len(p) >= 4 and n.startswith(p)) for p in prefixes):
                    kind = k
                    break
        if kind == "heartbeat" and not dark:
            kind = None
        if kind:
            cand.append({"kind": kind, "at": round(float(w["start"]), 2), "db": -14.0, "why": f"mot:{n}", "prio": 2})
    # Priorité 3 : souffles aux vrais changements de plan, espacés
    last_whoosh = -99.0
    for c in cuts:
        if c - last_whoosh >= cut_min_gap and 1.5 < c < duration - 1.5:
            if twist_t is not None and abs(c - twist_t) < 2.0:
                continue
            cand.append({"kind": "whoosh", "at": round(max(0.0, c - 0.25), 2), "db": -21.0, "why": "coupe", "prio": 3})
            last_whoosh = c

    cand.sort(key=lambda e: (e["prio"], e["at"]))
    kept: List[Dict[str, Any]] = []
    for e in cand:
        if len(kept) >= max_events:
            break
        if not (0.0 <= e["at"] < duration - 0.2):
            continue
        # Silence franc juste avant le twist (seul le « drop » y a droit)
        if twist_t is not None and e["why"] != "twist" and (twist_t - 0.8) < e["at"] < (twist_t + 0.4):
            continue
        if any(k["kind"] == e["kind"] and abs(k["at"] - e["at"]) < repeat_gap for k in kept):
            continue
        if any(abs(k["at"] - e["at"]) < 0.35 for k in kept):
            continue
        kept.append(e)
    kept.sort(key=lambda e: e["at"])
    for e in kept:
        e.pop("prio", None)
    return kept


def plan_hud(script: Dict[str, Any], duration: float, words: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Compteurs permanents (« ALTITUDE : 5 M ») : chaque étape reste affichée jusqu'à la suivante, calée sur la voix."""
    steps: List[Dict[str, Any]] = []
    for h in (script.get("hud") or []) if isinstance(script.get("hud"), list) else []:
        if not isinstance(h, dict):
            continue
        lines = [str(x).strip()[:40] for x in (h.get("lines") or []) if str(x).strip()][:2]
        if not lines:
            continue
        st = 0.0 if not steps else -1.0
        if h.get("at_phrase") and words:
            idx = _find_phrase(words, str(h["at_phrase"]))
            if idx >= 0:
                st = float(words[idx]["start"])
        if st < 0:
            try:
                st = float(h.get("start", -1))
            except (TypeError, ValueError):
                st = -1.0
        if 0 <= st < duration:
            steps.append({"lines": lines, "start": round(st, 2)})
    steps.sort(key=lambda x: x["start"])
    for i, s in enumerate(steps):
        s["end"] = round(steps[i + 1]["start"] if i + 1 < len(steps) else duration, 2)
    return [s for s in steps if s["end"] > s["start"]][:12]


def plan_notes(
    script: Dict[str, Any],
    shots: List[Dict[str, Any]],
    raw_shots: Optional[List[Dict[str, Any]]],
    duration: float,
    hook_end: float,
    words: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Cartons de texte géants : `on_screen_notes` fournis ({text, at_phrase} calé sur la voix, ou {text, start}),
    sinon `text_overlay` courts du storyboard (max 4).
    """
    notes: List[Dict[str, Any]] = []
    given = script.get("on_screen_notes")
    if isinstance(given, list) and given:
        for n in given:
            if isinstance(n, dict) and n.get("text"):
                st = -1.0
                if n.get("at_phrase") and words:
                    idx = _find_phrase(words, str(n["at_phrase"]))
                    if idx >= 0:
                        st = float(words[idx]["start"])
                if st < 0:
                    try:
                        st = float(n.get("start", -1))
                    except (TypeError, ValueError):
                        st = -1.0
                if 0 <= st < duration:
                    try:
                        en = float(n.get("end") or (st + 2.6))
                    except (TypeError, ValueError):
                        en = st + 2.6
                    if en <= st:
                        en = st + 2.6
                    notes.append({"text": str(n["text"])[:60], "start": round(st, 2), "end": round(min(duration, en), 2)})
        if notes:
            return notes[:6]
    overlays = []
    for i, s in enumerate(raw_shots or []):
        if isinstance(s, dict):
            ov = str(s.get("text_overlay") or "").strip()
            if 2 <= len(ov) <= 32:
                overlays.append((i, ov))
    hook = str(script.get("hook_screen_text") or "").strip().lower()
    for i, ov in overlays:
        if ov.lower() == hook:
            continue
        a, _ = _parse_approx((raw_shots or [])[i].get("timestamp_approx", "")) if isinstance((raw_shots or [])[i], dict) else (-1.0, -1.0)
        if a < 0 and i < len(shots):
            a = shots[min(i, len(shots) - 1)]["start"]
        if a < hook_end + 0.3 or a > duration - 2.0:
            continue
        if notes and a - notes[-1]["end"] < 3.0:
            continue
        notes.append({"text": ov, "start": round(a, 2), "end": round(min(duration - 0.3, a + 2.4), 2)})
        if len(notes) >= 4:
            break
    return notes


def build_plan(
    script: Dict[str, Any],
    words: List[Dict[str, Any]],
    duration: float,
    shots: Optional[List[Dict[str, Any]]] = None,
    style_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Construit le plan de production complet d'une vidéo."""
    script = script or {}
    ov: Dict[str, Any] = {}
    if isinstance(script.get("production"), dict):
        ov.update(script["production"])
    if isinstance(style_overrides, dict):
        ov.update(style_overrides)

    text_all = f"{script.get('title', '')} {script.get('hook_screen_text', '')} {script.get('full_spoken_script', '')}"
    mood = ov.get("mood") or detect_mood(text_all)
    min_len = float(ov.get("shot_min_s", 1.6))
    max_len = float(ov.get("shot_max_s", 4.2))
    segs = align_shots(shots, words, duration, min_len=min_len, max_len=max_len)
    cuts = [s["start"] for s in segs[1:]]
    twist_t = find_twist_time(script, words, duration)
    cta = find_cta_times(words)
    hook_end = min(3.4, duration * 0.45)
    sfx = plan_sfx(
        cuts, words, twist_t, cta, duration, mood,
        max_events=int(ov.get("sfx_max", 20)),
        cut_min_gap=float(ov.get("whoosh_min_gap_s", 10.0)),
        repeat_gap=float(ov.get("sfx_repeat_gap_s", 4.0)),
    )
    music_db = float(ov.get("music_db", DEFAULT_MUSIC_DB.get(mood, -17.0)))
    lens = [s["end"] - s["start"] for s in segs] or [duration]
    return {
        "version": PLAN_VERSION,
        "mood": mood,
        "duration": round(float(duration), 2),
        "shots": segs,
        "cuts": cuts,
        "twist_t": round(twist_t, 2) if twist_t is not None else None,
        "cta_times": [round(t, 2) for t in cta],
        "sfx": sfx,
        "keywords": classify_keywords(script, words),
        "notes": plan_notes(script, segs, shots, duration, hook_end, words),
        "hud": plan_hud(script, duration, words) if ov.get("hud") else [],
        "hud_color": ov.get("hud_color") or "",
        "music": {
            "db": music_db,
            "cut_before_twist_s": float(ov.get("music_cut_before_twist_s", 0.6)) if twist_t is not None else 0.0,
        },
        "captions": {
            "mode": ov.get("caption_mode") if ov.get("caption_mode") in ("chunk", "one_word", "two_words", "none") else "chunk",
            "note_color": ov.get("note_color") or "",
            "note_look": ov.get("note_look") if ov.get("note_look") in ("text", "card") else "text",
            "keyword_colors": bool(ov.get("keyword_colors", True)),
            # « cine » : sous-titres des vidéos de référence (Montserrat Black géant, mots-clés Luckiest Guy colorés)
            "look": "cine" if (ov.get("caption_look") == "cine" or ov.get("visual_style") == "cine3d") else "",
        },
        "character_style": ov.get("character_style") or "r6",
        # le moteur Ciné étalonne déjà l'image (vignettage, grain) : pas de second assombrissement au montage
        "grade": "clean" if ov.get("visual_style") in ("explainer2d", "flat_vector", "cine3d") else ("glow" if ov.get("visual_style") == "paper2d" else "cinema"),
        "stats": {
            "shots": len(segs),
            "avg_shot_s": round(sum(lens) / len(lens), 2),
            "max_shot_s": round(max(lens), 2),
            "sfx": len(sfx),
        },
    }


def save_plan(plan: Dict[str, Any], path: str) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    return path
