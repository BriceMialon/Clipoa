"""
Moteur « Dessin à compteur » : une image vectorielle par temps fort (~0,8 s), dessinée en SVG.

1. Découpe de la voix en images courtes (frontières de mots, ~0,8 s).
2. Claude DÉCRIT chaque image en JSON (persos, expression, pose, lieu, cadrage, bulle, compteur) ;
   il n'écrit aucun code : le dessin est fait par core/toon_kit.py (rien d'exécuté venant de l'IA).
3. Chrome sans fenêtre (Playwright) transforme chaque SVG en image ; FFmpeg ajoute un léger zoom
   par image et l'en-tête fixe (titre, sous-titre, pastille compteur), puis assemble la vidéo de fond.
Si l'IA ne répond pas, une mise en scène est déduite du texte (aucun échec bloquant).
"""
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config import BASE_DIR, FFMPEG_PATH
from core import toon_kit as K

FPS = 30
FONTS_DIR = BASE_DIR / "assets" / "fonts"
PANEL_TARGET_S = 0.7
PANEL_MIN_S = 0.45
PANEL_MAX_S = 1.4
# Mode « Rapide » choisi dans la Fabrique : environ 2x moins d'images à décrire (moins de tokens) et à dessiner
FAST_PANEL_TIMING = {"target": 1.4, "min_len": 0.8, "max_len": 2.4}

# Deux mises en page du même moteur : « compteur » (une image toutes les ~0,8 s) et « parable » (Parabole à 3 destins :
# plans de 4-6 s, bandeau de chapitre, objets qui apparaissent pendant le plan, carton final « Et toi ? »).
MODES = {
    "compteur": {"target": PANEL_TARGET_S, "min": PANEL_MIN_S, "max": PANEL_MAX_S},
    "parable": {"target": 4.2, "min": 2.4, "max": 6.5},
}


def mode_params(mode: Optional[str]) -> Dict[str, float]:
    return MODES.get(mode or "compteur", MODES["compteur"])


# ───────────────────────────── Découpe en images ─────────────────────────────

def build_panels(words: List[Dict[str, Any]], duration: float, beat_starts: Optional[List[float]] = None,
                 target: float = PANEL_TARGET_S, min_len: float = PANEL_MIN_S, max_len: float = PANEL_MAX_S) -> List[Dict[str, Any]]:
    """Images calées sur les débuts de mots : une nouvelle image toutes les ~0,8 s, et à chaque nouveau plan."""
    duration = max(0.5, float(duration))
    ws = [w for w in (words or []) if isinstance(w, dict) and "start" in w]
    beats = sorted(float(b) for b in (beat_starts or []) if 0 < float(b) < duration)
    starts = [0.0]
    sentence_cuts = target >= 2.0
    for prev_w, w in zip(ws, ws[1:]):
        t = float(w["start"])
        if t >= duration - min_len:
            break
        since = t - starts[-1]
        at_beat = any(abs(t - b) < 0.12 for b in beats)
        # plans longs (Parabole) : on coupe de préférence en fin de phrase
        at_sentence = sentence_cuts and re.search(r"[.!?…]$", str(prev_w.get("word", "")).strip()) is not None
        if sentence_cuts:
            cut = since >= min_len and (at_sentence or at_beat or since >= max_len * 0.9)
        else:
            cut = since >= min_len and (since >= target or at_beat)
        if cut:
            starts.append(t)
    # trous sans mots trop longs (silence, musique) : coupés régulièrement
    filled = []
    bounds = starts + [duration]
    for a, b in zip(bounds, bounds[1:]):
        filled.append(a)
        n = int((b - a) // max_len)
        for k in range(1, n + 1):
            t = a + k * (b - a) / (n + 1)
            if b - t >= min_len:
                filled.append(t)
    starts = sorted(set(round(s, 3) for s in filled))
    panels = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else duration
        txt = " ".join(str(w.get("word", "")).strip() for w in ws if s - 0.01 <= float(w["start"]) < e - 0.01)
        panels.append({"i": i, "start": round(s, 3), "end": round(e, 3), "text": txt})
    if len(panels) > 1 and panels[-1]["end"] - panels[-1]["start"] < min_len:
        last = panels.pop()
        panels[-1]["end"] = last["end"]
        panels[-1]["text"] = (panels[-1]["text"] + " " + last["text"]).strip()
    return panels


# ───────────────────────────── Mise en scène par l'IA ─────────────────────────────

def build_prompt(script: Dict[str, Any], panels: List[Dict[str, Any]], da_hint: str = "", mode: str = "compteur") -> str:
    if mode == "parable":
        return build_parable_prompt(script, panels, da_hint)
    lines = "\n".join(f'{p["i"]}|{p["end"] - p["start"]:.1f}s|{p["text"]}' for p in panels)
    title = script.get("title") or ""
    hook = script.get("hook_screen_text") or ""
    da = (da_hint or "")[:1800]
    sb = []
    for sh in (script.get("visual_storyboard") or [])[:14]:
        if isinstance(sh, dict):
            d = str(sh.get("visual") or sh.get("description") or sh.get("desc") or "").strip()
            if d:
                sb.append("- " + d[:160])
    board = ("Storyboard du script (respecte les tenues et les personnages décrits) :\n" + "\n".join(sb)) if sb else ""
    return f"""Tu es le dessinateur d'un short vertical en DESSIN VECTORIEL façon « brainrot » : persos chibi (grosse tête ronde,
grands yeux, joues roses, souvent casquette et lunettes rondes), contours épais, aplats, UNE image fixe par temps fort
(~0,8 s), une nouvelle expression ou un nouveau cadrage à CHAQUE image. Un en-tête fixe en haut résume la règle de la vidéo
et une pastille COMPTEUR évolue pendant l'histoire (ex. « TON SILENCE : 11 MIN », « TES EXCUSES : 4 »).
Tu ne dessines rien toi-même : tu DÉCRIS chaque image en JSON, un programme la dessine.

Titre : {title}
Accroche : {hook}
{('Direction artistique du style :' + chr(10) + da) if da else ''}
{board}

Voici les {len(panels)} images, une par ligne : numéro|durée|texte dit pendant l'image.
{lines}

Réponds UNIQUEMENT avec ce JSON (aucun texte autour) :
{{
 "header": {{"title": "4 à 6 mots, la règle ou le concept (ex. ICI, TON SILENCE SE VOIT)",
            "subtitle": "la règle en chiffres, court (ex. 10 MIN SANS PARLER = TRANSPARENT)",
            "counter_label": "ce qu'on compte, 1 à 3 mots (ex. TON SILENCE), ou vide si rien ne se compte",
            "counter_unit": "unité courte (MIN, J, €, …) ou vide", "accent": "#F0508C"}},
 "cast": [{{"id": "hero", "name": "Yanis", "skin": "#F6D3B3", "hair": "#3B2A20", "hair_style": "short",
           "top": "#3F8E5E", "top_style": "hoodie", "pants": "#3C4A66", "cap": "#F4B63F", "glasses": true}}],
 "locations": [{{"id": "camp", "kind": "park_day", "label": ""}}],
 "cards": {{"regles": {{"title": "Règlement de la colo", "items": [["Article 1", "Ici, tout le monde participe."]], "sign": "Les moniteurs"}}}},
 "panels": [{{"i": 0, "loc": "camp", "f": "close", "c": [{{"id": "hero", "e": "shocked", "p": "arms_up", "n": 10, "say": "", "g": 0}}],
             "crowd": 0, "k": 10, "prop": "", "pl": "", "card": "", "hi": 0}}]
}}

Règles :
- cast : 1 à 6 persos récurrents, chacun reconnaissable (couleurs de peau, cheveux, haut, casquette différentes).
  skin parmi {", ".join(K.SKINS)} ; hair_style parmi {", ".join(K.HAIR_STYLES)} ; top_style parmi {", ".join(K.TOP_STYLES)} ;
  "cap" = couleur de casquette ou null (le compteur s'affiche SUR la casquette), "glasses" true/false.
- locations : 1 à 5 lieux ; kind parmi {", ".join(K.LOCATIONS)} ; "label" = panneau court sur le décor (ex. DORTOIR) ou vide.
- panels : EXACTEMENT {len(panels)} entrées, "i" de 0 à {len(panels) - 1}, dans l'ordre.
  "f" (cadrage) parmi close (gros plan d'UN perso, le plus fréquent), medium (2-3 persos), wide (groupe + "crowd" figurants 0-8),
  card (carton texte plein écran : "card" = clé de "cards", "hi" = numéro de l'article mis en avant), object (gros objet : "prop" parmi
  {", ".join(K.PROPS)}, "pl" = petit texte sur l'objet).
  "c" = persos à l'image : "e" expression parmi {", ".join(K.EXPRESSIONS)} ; "p" pose parmi {", ".join(K.POSES)} ;
  "n" = valeur du compteur sur SA casquette (nombre) ; "say" = bulle de 1 à 3 mots (rare, max 1 image sur 5) ;
  "g" = transparence 0 à 0.8 (ex. un perso qui « disparaît »).
  "k" = valeur de la pastille compteur de l'en-tête à cette image (nombre, elle évolue avec l'histoire).
- Cohérence : le héros (premier perso de "cast") est celui dont parle la voix ; quand la phrase parle de lui, IL est à l'image.
  Son apparence ne change jamais. "n" sur une casquette = l'état de CE perso (le héros porte la valeur de "k") ; un perso
  secondaire a sa propre valeur, jamais celle du héros. Quand "k" change, montre le héros au même moment.
  Quand le compteur change beaucoup, passe par des valeurs intermédiaires sur plusieurs images.
- Rythme « brainrot » : alterne gros plans et plans larges, change d'expression à chaque image, réactions exagérées,
  l'image montre ce que dit la voix (un nom = un objet ou un perso visible). 1 carton tous les ~15 s maximum.
- Textes en français, sans emoji."""


def build_parable_prompt(script: Dict[str, Any], panels: List[Dict[str, Any]], da_hint: str = "") -> str:
    """Parabole à 3 destins : même départ, trois choix, trois destins, puis la morale et « Et toi ? »."""
    lines = "\n".join(f'{p["i"]}|{p["end"] - p["start"]:.1f}s|{p["text"]}' for p in panels)
    da = (da_hint or "")[:1500]
    return f"""Tu es le dessinateur d'un short vertical en DESSIN VECTORIEL PLAT, format « parabole à 3 destins » : au départ,
trois personnages reçoivent la même chose ; chacun fait un choix différent ; on suit les trois destins ; la morale arrive à la fin.
Images calmes et lisibles : UNE image par phrase (4 à 6 s), sur laquelle 1 ou 2 objets « apparaissent » pendant la phrase.
Un bandeau de chapitre en haut dit où on en est (« N°1 : IL LE DÉPENSE »). La dernière image est un carton « ET TOI ? »
qui reprend les choix en icônes pour faire commenter. Tu ne dessines rien toi-même : tu DÉCRIS chaque image en JSON.

Titre : {script.get("title") or ""}
Accroche : {script.get("hook_screen_text") or ""}
{('Direction artistique du style :' + chr(10) + da) if da else ''}

Voici les {len(panels)} images, une par ligne : numéro|durée|texte dit pendant l'image.
{lines}

Réponds UNIQUEMENT avec ce JSON (aucun texte autour) :
{{
 "header": {{"title": "la question de départ, 3 à 7 mots (ex. POURQUOI CERTAINS S'EN SORTENT ?)", "accent": "#FFD23F"}},
 "cast": [{{"id": "p1", "name": "Léo", "skin": "#F6D3B3", "hair": "#3B2A20", "hair_style": "short", "top": "#4E7FCB",
           "top_style": "tshirt", "pants": "#3C4A66", "cap": null, "glasses": false}}],
 "locations": [{{"id": "rue", "kind": "street", "label": ""}}],
 "choices": {{"title": "ET TOI ?", "items": [{{"prop": "plate", "label": "DÉPENSER"}}, {{"prop": "piggy", "label": "GARDER"}}, {{"prop": "plant", "label": "FAIRE GRANDIR"}}]}},
 "panels": [{{"i": 0, "loc": "rue", "f": "medium", "ch": "", "c": [{{"id": "p1", "e": "happy", "p": "wave"}}],
             "prop": "", "pl": "", "pops": [{{"prop": "coin", "label": "", "at": "top"}}]}}]
}}

Règles :
- cast : EXACTEMENT 3 personnages principaux (les trois destins), très reconnaissables (haut de couleur différente), + 1 ou 2 secondaires si besoin.
  skin parmi {", ".join(K.SKINS)} ; hair_style parmi {", ".join(K.HAIR_STYLES)} ; top_style parmi {", ".join(K.TOP_STYLES)} ;
  "cap" = couleur de casquette ou null, "glasses" true/false.
- locations : 1 à 4 lieux ; kind parmi {", ".join(K.LOCATIONS)} ; "label" = panneau court ou vide.
- panels : EXACTEMENT {len(panels)} entrées, "i" de 0 à {len(panels) - 1}, dans l'ordre.
  "f" parmi medium (2-3 persos, le plus fréquent), wide (les 3 + "crowd" figurants 0-8), close (UN perso, pour son destin),
  object (gros objet qui explique : "prop" parmi {", ".join(K.PROPS)}, "pl" = petit texte, ex. un tableau « chalkboard » ou
  une courbe « chart_up » / « chart_down »), choices (le carton final, UNE seule fois, sur la DERNIÈRE image).
  "c" = persos : "e" expression parmi {", ".join(K.EXPRESSIONS)} ; "p" pose parmi {", ".join(K.POSES)} ; "say" = bulle 1 à 3 mots (rare).
  "ch" = texte du bandeau de chapitre, 2 à 5 mots en majuscules (« N°1 : IL LE DÉPENSE », « N°2 : IL LE GARDE »,
  « N°3 : IL LE FAIT GRANDIR », « LA MORALE ») ; vide pendant l'introduction. Le même texte reste tant qu'on est dans le chapitre.
  "pops" = 0 à 2 objets qui apparaissent pendant la phrase : "prop" parmi la même liste, "label" court, "at" parmi
  {", ".join(K.POP_SLOTS)} (ne cache pas les visages : préfère top).
- L'image montre ce que dit la voix : un nom = un objet visible. Pendant le chapitre N°1, c'est le perso 1 qu'on voit, etc.
  L'objet commun du départ revient dans chaque destin (multiplié, disparu, grandi…).
- Persos, objets et lieux sont les TIENS : n'imite aucune chaîne ni aucun personnage existant.
- Textes en français, sans emoji."""


def _num(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    s = str(v).strip()[:6]
    return s if re.match(r"^-?[0-9]+([.,][0-9]+)?$", s) else None


def _short(v: Any, n: int) -> str:
    return re.sub(r"[\x00-\x1f<>]", "", str(v or "")).strip()[:n]


def _pops(v: Any) -> List[Dict[str, Any]]:
    out = []
    for p in (v or [])[:2] if isinstance(v, list) else []:
        if isinstance(p, dict) and p.get("prop") in K.PROPS:
            out.append({"prop": p["prop"], "label": _short(p.get("label"), 10), "at": p.get("at") if p.get("at") in K.POP_SLOTS else "top"})
    return out


def _choices(v: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(v, dict):
        return None
    items = [{"prop": it["prop"], "label": _short(it.get("label"), 14)} for it in (v.get("items") or [])[:3]
             if isinstance(it, dict) and it.get("prop") in K.PROPS]
    if len(items) < 2:
        return None
    return {"title": _short(v.get("title"), 20) or "ET TOI ?", "items": items, "accent": K.hexcol(v.get("accent"), "#FFD23F")}


def sanitize(raw: Dict[str, Any], n: int, mode: str = "compteur") -> Optional[Dict[str, Any]]:
    """Ne garde que des valeurs connues et bornées ; None si inutilisable."""
    if not isinstance(raw, dict) or not isinstance(raw.get("panels"), list) or not raw["panels"]:
        return None
    h = raw.get("header") if isinstance(raw.get("header"), dict) else {}
    header = {"title": _short(h.get("title"), 34), "subtitle": _short(h.get("subtitle"), 46),
              "counter_label": _short(h.get("counter_label"), 22), "counter_unit": _short(h.get("counter_unit"), 8),
              "accent": K.hexcol(h.get("accent"), K.PINK)}
    cast: Dict[str, Dict[str, Any]] = {}
    for i, c in enumerate((raw.get("cast") or [])[:6]):
        if not isinstance(c, dict):
            continue
        cid = _short(c.get("id") or f"p{i}", 20)
        cast[cid] = {
            "name": _short(c.get("name"), 20),
            "skin": K.hexcol(c.get("skin"), K.SKINS[i % len(K.SKINS)]),
            "hair": K.hexcol(c.get("hair"), K.HAIRS[i % len(K.HAIRS)]),
            "hair_style": c.get("hair_style") if c.get("hair_style") in K.HAIR_STYLES else "short",
            "top": K.hexcol(c.get("top"), K.TOPS[i % len(K.TOPS)]),
            "top_style": c.get("top_style") if c.get("top_style") in K.TOP_STYLES else "hoodie",
            "pants": K.hexcol(c.get("pants"), "#3C4A66"),
            "cap": K.hexcol(c.get("cap"), K.CAPS[i % len(K.CAPS)]) if c.get("cap") else None,
            "glasses": bool(c.get("glasses")),
        }
    if not cast:
        cast = dict(_default_cast())
    locs: Dict[str, Dict[str, Any]] = {}
    for i, l in enumerate((raw.get("locations") or [])[:5]):
        if isinstance(l, dict):
            lid = _short(l.get("id") or f"l{i}", 20)
            locs[lid] = {"kind": l.get("kind") if l.get("kind") in K.LOCATIONS else "park_day", "label": _short(l.get("label"), 18),
                         "wall": K.hexcol(l.get("wall"), "") or None, "night": bool(l.get("night"))}
    if not locs:
        locs = {"main": {"kind": "park_day", "label": ""}}
    cards: Dict[str, Dict[str, Any]] = {}
    for key, cd in list((raw.get("cards") or {}).items())[:4] if isinstance(raw.get("cards"), dict) else []:
        if isinstance(cd, dict):
            items = []
            for it in (cd.get("items") or [])[:4]:
                if isinstance(it, (list, tuple)) and it:
                    items.append([_short(it[0], 30), _short(it[1] if len(it) > 1 else "", 90)])
                elif isinstance(it, dict):
                    items.append([_short(it.get("head"), 30), _short(it.get("text"), 90)])
            cards[_short(key, 20)] = {"title": _short(cd.get("title"), 40), "items": items, "sign": _short(cd.get("sign"), 30)}
    choices = _choices(raw.get("choices"))
    first_loc = next(iter(locs))
    first_cast = next(iter(cast))
    panels: List[Dict[str, Any]] = []
    by_i = {}
    for p in raw["panels"]:
        if isinstance(p, dict):
            try:
                by_i.setdefault(int(p.get("i", len(by_i))), p)
            except (TypeError, ValueError):
                continue
    prev = None
    for i in range(n):
        p = by_i.get(i)
        if p is None:
            p = dict(prev or {}, i=i)
        f = p.get("f") or p.get("frame")
        f = f if f in K.FRAMES else "medium"
        if f == "choices" and not choices:
            f = "medium"
        chars = []
        for c in (p.get("c") or p.get("chars") or [])[:5]:
            if not isinstance(c, dict):
                continue
            cid = _short(c.get("id"), 20)
            if cid not in cast:
                continue
            e, po = c.get("e") or c.get("expr"), c.get("p") or c.get("pose")
            try:
                g = max(0.0, min(0.8, float(c.get("g") or c.get("ghost") or 0)))
            except (TypeError, ValueError):
                g = 0.0
            chars.append({"id": cid, "expr": e if e in K.EXPRESSIONS else "neutral", "pose": po if po in K.POSES else "idle",
                          "counter": _num(c.get("n") if "n" in c else c.get("counter")), "say": _short(c.get("say"), 24), "ghost": g})
        if f in ("close", "medium", "wide") and not chars:
            chars = [{"id": first_cast, "expr": "neutral", "pose": "idle", "counter": None, "say": "", "ghost": 0.0}]
        card = None
        if f == "card":
            card = dict(cards.get(_short(p.get("card"), 20)) or next(iter(cards.values()), None) or {})
            if not card:
                f = "close"
                chars = chars or [{"id": first_cast, "expr": "neutral", "pose": "idle", "counter": None, "say": "", "ghost": 0.0}]
            else:
                hi = p.get("hi")
                card["hi"] = int(hi) if isinstance(hi, (int, float)) or (isinstance(hi, str) and hi.isdigit()) else None
        try:
            crowd = max(0, min(8, int(p.get("crowd") or 0)))
        except (TypeError, ValueError):
            crowd = 0
        loc = _short(p.get("loc"), 20)
        out = {"i": i, "frame": f, "loc": loc if loc in locs else first_loc, "chars": chars, "crowd": crowd,
               "counter": _num(p.get("k") if "k" in p else p.get("counter")), "prop": p.get("prop") if p.get("prop") in K.PROPS else "",
               "prop_label": _short(p.get("pl") or p.get("prop_label"), 14), "card": card}
        if mode == "parable":
            out["chapter"] = _short(p.get("ch") or p.get("chapter"), 30)
            out["pops"] = _pops(p.get("pops"))
            out["choices"] = choices if f == "choices" else None
        panels.append(out)
        prev = p
    if mode == "parable" and choices and panels and not any(p["frame"] == "choices" for p in panels):
        # le carton « Et toi ? » termine toujours la parabole
        panels[-1].update(frame="choices", choices=choices, chars=[], pops=[])
    return {"header": header, "cast": cast, "locations": locs, "cards": cards, "choices": choices, "panels": panels}


def _default_cast() -> Dict[str, Dict[str, Any]]:
    return {
        "hero": {"skin": K.SKINS[0], "hair": K.HAIRS[2], "hair_style": "short", "top": "#3F8E5E", "top_style": "hoodie", "cap": "#F4B63F", "glasses": True},
        "ami": {"skin": K.SKINS[4], "hair": K.HAIRS[1], "hair_style": "short", "top": "#E8823A", "top_style": "vest", "cap": "#3D6FCB", "glasses": False},
        "amie": {"skin": K.SKINS[2], "hair": K.HAIRS[0], "hair_style": "long", "top": "#E86FA6", "top_style": "tshirt", "cap": None, "glasses": False},
    }


def heuristic_parable(script: Dict[str, Any], panels: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Parabole sans IA : intro, 3 chapitres (un perso chacun), morale, carton final."""
    cast = _default_cast()
    cast["ami"]["cap"] = None
    ids = list(cast)
    n = len(panels)
    choices = {"title": "ET TOI ?", "accent": "#FFD23F",
               "items": [{"prop": "plate", "label": "DÉPENSER"}, {"prop": "piggy", "label": "GARDER"}, {"prop": "plant", "label": "FAIRE GRANDIR"}]}
    body = max(1, n - 2)
    out = []
    for p in panels:
        i = p["i"]
        part = 0 if i == 0 else min(4, 1 + (i - 1) * 3 // body) if i < n - 1 else 5
        t = p.get("text") or ""
        e = "shocked" if "?" in t else ("laugh" if "!" in t else ("talk", "happy", "worried", "think")[i % 4])
        if part in (1, 2, 3):
            who = ids[part - 1]
            chars = [{"id": who, "expr": e, "pose": ("idle", "point", "shrug", "cheer")[i % 4], "counter": None, "say": "", "ghost": 0.0}]
            frame, ch = "close" if i % 2 else "medium", f"N°{part}"
        else:
            chars = [{"id": c, "expr": e, "pose": "idle", "counter": None, "say": "", "ghost": 0.0} for c in ids]
            frame, ch = "medium", ("LA MORALE" if part == 4 else "")
        out.append({"i": i, "frame": "choices" if part == 5 else frame, "loc": "main", "chars": [] if part == 5 else chars,
                    "crowd": 0, "counter": None, "prop": "", "prop_label": "", "card": None, "chapter": ch,
                    "pops": [{"prop": "coin", "label": "", "at": "top"}] if part in (1, 2, 3) else [],
                    "choices": choices if part == 5 else None})
    title = _short(script.get("hook_screen_text") or script.get("title") or "", 34)
    return {"header": {"title": title, "subtitle": "", "counter_label": "", "counter_unit": "", "accent": "#FFD23F"},
            "cast": cast, "locations": {"main": {"kind": "street", "label": ""}}, "cards": {}, "choices": choices, "panels": out}


def heuristic_spec(script: Dict[str, Any], panels: List[Dict[str, Any]], mode: str = "compteur") -> Dict[str, Any]:
    """Mise en scène sans IA : héros + amis, cadrages alternés, expression déduite de la ponctuation."""
    if mode == "parable":
        return heuristic_parable(script, panels)
    cast = _default_cast()
    ids = list(cast)
    cycle = ("close", "medium", "close", "wide", "close", "medium")
    out = []
    for p in panels:
        t = p.get("text") or ""
        e = "shocked" if "?" in t else ("laugh" if "!" in t else ("talk", "happy", "worried", "smug")[p["i"] % 4])
        f = cycle[p["i"] % len(cycle)]
        chars = [{"id": ids[0], "expr": e, "pose": ("idle", "arms_up", "point", "shrug")[p["i"] % 4], "counter": None, "say": "", "ghost": 0.0}]
        if f in ("medium", "wide"):
            chars.append({"id": ids[1 + p["i"] % 2], "expr": "laugh" if e != "laugh" else "shocked", "pose": "idle", "counter": None, "say": "", "ghost": 0.0})
        out.append({"i": p["i"], "frame": f, "loc": "main", "chars": chars, "crowd": 4 if f == "wide" else 0, "counter": None,
                    "prop": "", "prop_label": "", "card": None})
    title = _short(script.get("hook_screen_text") or script.get("title") or "", 34)
    return {"header": {"title": title, "subtitle": "", "counter_label": "", "counter_unit": "", "accent": K.PINK},
            "cast": cast, "locations": {"main": {"kind": "park_day", "label": ""}}, "cards": {}, "panels": out}


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    txt = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt)
    if m:
        txt = m.group(1)
    try:
        return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
    except Exception:
        return None


def design(script: Dict[str, Any], panels: List[Dict[str, Any]], model: Optional[str] = None, da_hint: str = "",
           mode: str = "compteur") -> Dict[str, Any]:
    raw = ""
    try:
        from core.claude_bridge import ClaudeBridge
        raw = ClaudeBridge.query(build_prompt(script, panels, da_hint, mode), action="toon_design", model=model)
    except Exception as e:
        print(f"⚠️ Mise en scène IA indisponible ({e}) : mise en scène déduite du texte.")
    spec = sanitize(_parse_json(raw) or {}, len(panels), mode) if raw else None
    if spec:
        spec["_source"] = "ia"
        return spec
    spec = heuristic_spec(script, panels, mode)
    spec["_source"] = "texte"
    return spec


# ───────────────────────────── Rendu ─────────────────────────────

def is_available() -> bool:
    try:
        import playwright  # noqa: F401
    except Exception:
        return False
    return (FONTS_DIR / "Fredoka-Bold.ttf").exists()


def _font_css() -> str:
    css = []
    for fname, weights in (("Fredoka-Bold.ttf", (600, 700, 800)), ("Fredoka-Medium.ttf", (400, 500))):
        p = FONTS_DIR / fname
        if not p.exists():
            continue
        b64 = base64.b64encode(p.read_bytes()).decode()
        for w in weights:
            css.append(f"@font-face{{font-family:'{K.FONT}';font-weight:{w};src:url(data:font/ttf;base64,{b64}) format('truetype');}}")
    return "".join(css)


class Rasterizer:
    """Chrome sans fenêtre : SVG -> PNG 1080x1920 (fond transparent possible)."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        exe = None
        try:
            from core.cine_setup import find_chrome
            exe = find_chrome()
        except Exception:
            exe = os.environ.get("CLIPOA_CHROME") or None
        args = ["--no-sandbox", "--disable-gpu", "--font-render-hinting=none"]
        self._browser = self._pw.chromium.launch(executable_path=exe, args=args) if exe else self._pw.chromium.launch(args=args)
        self._page = self._browser.new_page(viewport={"width": K.W, "height": K.H}, device_scale_factor=1)
        self._page.set_content(f"<html><head><style>{_font_css()} html,body{{margin:0;background:transparent;overflow:hidden}}</style></head>"
                               f"<body><div id='s'></div></body></html>")
        return self

    def png(self, svg: str, path: str, transparent: bool = False) -> str:
        self._page.evaluate("s => { document.getElementById('s').innerHTML = s; }", svg)
        self._page.evaluate("() => document.fonts.ready.then(() => true)")
        self._page.screenshot(path=path, omit_background=transparent, clip={"x": 0, "y": 0, "width": K.W, "height": K.H})
        return path

    def __exit__(self, *a):
        try:
            self._browser.close()
        finally:
            self._pw.stop()


ZOOMS = {"close": (1.0, 1.07), "medium": (1.02, 1.08), "wide": (1.09, 1.02), "card": (1.0, 1.03), "object": (1.0, 1.1),
         "choices": (1.0, 1.04)}


def _segment(scene_png: str, header_png: Optional[str], frames: int, frame: str, idx: int, out: str,
             zrange: Optional[tuple] = None) -> None:
    z0, z1 = ZOOMS.get(frame, (1.0, 1.06))
    if idx % 3 == 2 and frame == "close":
        z0, z1 = z1, z0
    if zrange:
        z0, z1 = (round(z0 + (z1 - z0) * zrange[0], 4), round(z0 + (z1 - z0) * zrange[1], 4))
    n = max(1, frames)
    up_w, up_h = 1620, 2880
    zexpr = f"{z0}+({z1}-{z0})*on/{max(1, n - 1)}"
    vf = (f"[0:v]scale={up_w}:{up_h}:flags=lanczos,zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih*0.46-(ih/zoom*0.46)':d={n}:s={K.W}x{K.H}:fps={FPS}[bg]")
    inputs = ["-i", scene_png]
    if header_png:
        inputs += ["-i", header_png]
        vf += ";[bg][1:v]overlay=0:0:format=auto[v]"
    else:
        vf += ";[bg]null[v]"
    cmd = [FFMPEG_PATH, "-y", "-loglevel", "error", *inputs, "-filter_complex", vf, "-map", "[v]", "-frames:v", str(n),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), out]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg (image {idx}) : {res.stderr[-400:]}")


def _parable_header(header: Dict[str, Any], sp: Dict[str, Any]) -> tuple:
    """Parabole : bandeau du chapitre en cours, sinon la question de départ ; rien sur le carton final."""
    if sp.get("frame") == "choices":
        return "", ""
    ch = sp.get("chapter") or ""
    if ch:
        return "ch:" + ch, K.chapter_svg(ch, "#FFFFFF")
    t = header.get("title") or ""
    return ("t:" + t, K.header_svg({"title": t, "accent": header.get("accent")})) if t else ("", "")


def render_video(spec: Dict[str, Any], panels: List[Dict[str, Any]], duration: float, out_mp4: str,
                 progress: Optional[Callable[[int, str], None]] = None, work_dir: Optional[str] = None,
                 mode: str = "compteur") -> str:
    """Dessine chaque image, ajoute zoom + en-tête, assemble la vidéo de fond (sans son)."""
    tmp = Path(work_dir or tempfile.mkdtemp(prefix="toon_"))
    tmp.mkdir(parents=True, exist_ok=True)
    header = spec.get("header") or {}
    unit = header.get("counter_unit") or ""
    cast, locs = spec.get("cast") or {}, spec.get("locations") or {}
    pspec = spec.get("panels") or []
    n = len(panels)
    headers: Dict[str, str] = {}
    scenes: List[List[str]] = []
    counter = None
    with Rasterizer() as R:
        for k, p in enumerate(panels):
            sp = dict(pspec[k] if k < len(pspec) else pspec[-1])
            sp["_unit"] = unit
            if sp.get("counter") is not None:
                counter = sp["counter"]
            loc = locs.get(sp.get("loc")) or next(iter(locs.values()), {"kind": "park_day"})
            seed = 7 + list(locs).index(sp.get("loc")) if sp.get("loc") in locs else 7
            # objets qui apparaissent pendant le plan (Parabole) : une image par étape, le zoom continue d'une étape à l'autre
            pops = sp.get("pops") or []
            states = []
            for j in range(len(pops) + 1):
                st = dict(sp, pops=pops[:j])
                states.append(R.png(K.wrap_svg(K.panel_svg(st, cast, loc, seed=seed)), str(tmp / f"s{k:03d}_{j}.png")))
            scenes.append(states)
            if mode == "parable":
                key, hsvg = _parable_header(header, sp)
            else:
                key = str(counter)
                hsvg = K.header_svg(header, counter) if (header.get("title") or header.get("counter_label")) else ""
            if hsvg and key not in headers:
                headers[key] = R.png(K.wrap_svg(hsvg), str(tmp / f"h{len(headers):03d}.png"), transparent=True)
            p["_header"] = headers.get(key) if hsvg else None
            if progress and (k % 10 == 0 or k == n - 1):
                progress(58 + int(8 * (k + 1) / max(1, n)), f"🖍️ [3/4] Dessin des images… {k + 1}/{n}")
    segs = []
    f_prev = 0
    for k, p in enumerate(panels):
        f_end = int(round((p["end"] if k < n - 1 else duration) * FPS))
        frames = max(1, f_end - f_prev)
        f_prev = f_end
        sp = pspec[k] if k < len(pspec) else pspec[-1]
        states = scenes[k]
        m = len(states)
        if m > 1 and frames < m * 12:
            states, m = states[-1:], 1  # plan trop court pour faire apparaître les objets un par un
        done = 0
        for j, png in enumerate(states):
            nf = frames - done if j == m - 1 else frames * (j + 1) // m - done
            seg = str(tmp / f"v{k:03d}_{j}.mp4")
            _segment(png, p.get("_header"), nf, sp.get("frame", "medium"), k, seg,
                     zrange=(done / frames, (done + nf) / frames) if m > 1 else None)
            done += nf
            segs.append(seg)
        if progress and (k % 10 == 0 or k == n - 1):
            progress(66 + int(8 * (k + 1) / max(1, n)), f"🎞️ [3/4] Montage des images… {k + 1}/{n}")
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{Path(s).name}'\n" for s in segs), encoding="utf-8")
    res = subprocess.run([FFMPEG_PATH, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", out_mp4],
                         capture_output=True, text=True, timeout=300, cwd=str(tmp))
    if res.returncode != 0 or not os.path.exists(out_mp4):
        raise RuntimeError(f"Assemblage impossible : {res.stderr[-400:]}")
    if not work_dir:
        shutil.rmtree(tmp, ignore_errors=True)
    return out_mp4


def render_story(session_id: str, script: Dict[str, Any], plan: Dict[str, Any], words: List[Dict[str, Any]],
                 duration: float, out_dir: Path, model: Optional[str] = None, da_hint: str = "",
                 progress: Optional[Callable[[int, str], None]] = None, mode: str = "compteur",
                 quality: str = "hq") -> str:
    """Point d'entrée du pipeline : renvoie la vidéo de fond (mp4 sans son).
    quality « fast » (mode compteur seulement) = images plus longues (~1,4 s) donc moins nombreuses ;
    « hq » = une image toutes les ~0,7 s. Le mode « parable » a déjà des plans longs."""
    beats = [float(s.get("start", 0)) for s in (plan.get("shots") or [])[1:]]
    mode = mode if mode in MODES else "compteur"
    if mode == "compteur" and quality == "fast":
        panels = build_panels(words, duration, beats, **FAST_PANEL_TIMING)
    else:
        mp = mode_params(mode)
        panels = build_panels(words, duration, beats, target=mp["target"], min_len=mp["min"], max_len=mp["max"])
    if progress:
        progress(55, f"🖍️ [3/4] Claude met en scène {len(panels)} images dessinées…")
    spec = design(script, panels, model=model, da_hint=da_hint, mode=mode)
    try:
        with open(Path(out_dir) / f"{session_id}_toon_spec.json", "w", encoding="utf-8") as f:
            json.dump({"panels_timing": panels, **spec}, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    out = str(Path(out_dir) / f"{session_id}_toon_bg.mp4")
    return render_video(spec, panels, duration, out, progress, mode=mode)
