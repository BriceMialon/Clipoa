"""
Metteur en scène Clipoa : l'IA choisie (Claude ou Antigravity) lit le script et décrit, en JSON, le décor
de CETTE vidéo (lieux, objets, panneaux, personnages, et pour chaque plan : lieu, cadrage, action).
Blender construit ensuite la scène dans le style choisi (core/blender_kit/scene_kit_bpy.py).

L'IA ne code pas la scène (ses scripts Blender plantaient souvent) : elle décrit, Blender construit.
Si l'IA ne répond pas ou répond mal, une description est déduite du storyboard (aucun échec bloquant).
"""
import json
import re
from typing import Any, Dict, List, Optional

LOCATION_TYPES = (
    "street", "village", "city", "vertical_city", "market", "house", "room", "school", "shop", "office",
    "hospital", "forest", "park", "field", "beach", "lake", "space", "stage",
)
PROP_KINDS = (
    "house", "townhall", "tree", "pine", "lamp", "car", "fountain", "castle", "mountain", "market", "gate",
    "table", "bed", "door", "sign", "fence", "rock", "box", "bench", "tv", "fridge", "coins", "ladder", "stage",
    "moon", "monitor", "desk", "shelf", "umbrella", "star", "tower", "stock_screen", "price_sign", "subscribe",
    "sofa", "armchair", "pancakes", "plate", "mug", "frame", "window", "rug", "bus", "snowman", "bookshelf", "mirror", "lamp_floor",
)
CAMERAS = ("drone", "wide", "medium", "close", "face", "low", "pov", "tilt", "back", "high")
EMOTIONS = ("neutral", "happy", "sad", "cry", "surprised", "scared", "angry", "smirk")
WEATHERS = ("none", "snow", "rain")
ACTIONS = ("idle", "walk", "run", "jump", "point", "fall", "sit")
CHAR_MODELS = {
    "villageois_01": "garçon, cheveux bruns, sweat orange, jean",
    "villageois_02": "garçon blond, sweat bleu",
    "villageois_03": "fille, bonnet rose, haut jaune, pantalon marron",
    "villageois_04": "garçon peau foncée, cheveux noirs, haut vert",
    "villageois_05": "garçon casquette rouge, haut violet",
    "villageois_06": "grand-père chauve, cheveux gris, pull orange",
    "villageois_07": "garçon peau foncée, bandeau, t-shirt blanc et orange",
    "villageois_08": "garçon blond, lunettes de soleil, haut rouge",
    "villageois_09": "garçon cheveux châtains, haut turquoise",
    "villageois_10": "fille cheveux bruns, haut rose",
    "marcel_vieux": "vieil homme, lunettes noires, canne, veste marron",
    "marcel_riche": "homme riche, costume bleu nuit, cravate dorée",
    "ours": "ours brun aux yeux rouges (monstre, menace)",
    "docteur_shark": "Docteur Shark, requin en sweat blanc, casquette bleue, lunettes violettes",
}
STYLE_HINTS = {
    "roblox": "3D en blocs façon Roblox, couleurs vives, personnages R6.",
    "paper2d": "stickmen 2D (tête ovale blanche, yeux points, petit pull coloré, membres en traits) dans un monde 3D à contours encre ; "
               "contraste froid dehors / chaud dedans ; un « show » (objet ou mot) à CHAQUE plan pour chaque nom dit ; "
               "« others » rempli dès que possible (2-3 persos à l'écran) ; donne un « hat » signature à chaque perso.",
    "flat_vector": "illustration vectorielle plate ultra-saturée (violet, bleu, vert, rose, orange), monde vertical : plus on est riche, plus on vit haut.",
    "explainer2d": "dessin animé vectoriel pastel vu de face (ciel bleu pâle, soleil, collines vert sauge, sol beige, rose framboise en accent), "
                   "personnages simples tête ronde ; utilise « hat » comme couleur de tablier/salopette ; un lieu = un décor plein cadre ; "
                   "les commerces ont une enseigne (sign_text = nom de la marque).",
}
_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _hex(v: Any) -> Optional[str]:
    s = str(v or "").strip()
    return ("#" + s.lstrip("#")) if _HEX.match(s) else None


def _shot_lines(plan: Dict[str, Any], words: Optional[List[Dict[str, Any]]]) -> List[str]:
    lines = []
    for s in plan.get("shots") or []:
        txt = ""
        if words:
            txt = " ".join(w["word"] for w in words if s["start"] - 0.05 <= float(w["start"]) < s["end"] - 0.05)
        lines.append(f'{s["index"]}. {s["start"]:.1f}-{s["end"]:.1f}s | dit : « {txt[:140]} » | storyboard : {str(s.get("desc") or "")[:120]}')
    return lines


def build_prompt(script: Dict[str, Any], plan: Dict[str, Any], style: str, words=None, da_hint: str = "") -> str:
    models = "\n".join(f"- {k} : {v}" for k, v in CHAR_MODELS.items())
    shots = "\n".join(_shot_lines(plan, words))
    return f"""Tu es le chef décorateur et le réalisateur d'un Short vertical rendu dans Blender.
Style visuel : {STYLE_HINTS.get(style, STYLE_HINTS['roblox'])}
{('Direction artistique (extrait) : ' + da_hint[:1500]) if da_hint else ''}

Script (titre : {script.get('title', '')}) :
{script.get('full_spoken_script', '')[:3000]}

Plans de la vidéo (déjà calés sur la voix) :
{shots}

Décris le décor de CETTE histoire (pas un décor générique). Réponds UNIQUEMENT avec un JSON valide :
{{
  "time_of_day": "day|sunset|night",
  "weather": "{'|'.join(WEATHERS)}",
  "palette": {{"sky": "#RRGGBB", "ground": "#RRGGBB", "accent": "#RRGGBB"}},
  "characters": [{{"id": "hero", "name": "prénom", "model": "un id de la liste", "shirt": "#RRGGBB", "pants": "#RRGGBB", "hat": "#RRGGBB ou none", "hair": "#RRGGBB", "skin": "#RRGGBB", "hair_style": "short|long|wig|bald", "accessory": "glasses|apron|none", "scale": 1.0}}],
  "locations": [{{"id": "court_id", "type": "{'|'.join(LOCATION_TYPES)}", "ground": "#RRGGBB", "wall": "#RRGGBB", "sign_text": "texte court ou vide",
                 "props": [{{"kind": "{'|'.join(PROP_KINDS)}", "count": 1, "color": "#RRGGBB", "text": "pour sign"}}]}}],
  "shots": [{{"i": 0, "location": "id d'un lieu", "camera": "{'|'.join(CAMERAS)}", "focus": "id perso", "others": ["id perso"], "action": "{'|'.join(ACTIONS)}", "emotion": "{'|'.join(EMOTIONS)}",
             "show": {{"kind": "un objet de la liste des objets, ou text", "text": "1 à 3 mots EN MAJUSCULES (pour text/sign)", "color": "#RRGGBB"}}}}]
}}
Règles : 2 à 5 lieux qui correspondent à l'histoire ; 1 à 5 personnages ; un objet ou panneau qui montre ce que dit chaque phrase
(panneaux en majuscules, 3 mots max) ; exactement un élément « shots » par plan listé (même numéro i) ; ne jamais enchaîner deux
fois le même cadrage ; premier plan en « drone » ou « wide » ; gros plan « close » ou très gros plan visage « face » sur les émotions
et la révélation ; « back » = vu de dos (le perso regarde un objet : télé, porte, lac) ; « high » = plongée.
« show » = ce que la phrase de CE plan raconte, montré À L'IMAGE au moment exact où elle est dite (un objet qui apparaît à côté du perso :
une voiture quand on parle de voiture, des pièces quand on parle d'argent, un panneau « INTERDIT » pour une règle, ou « text » = un grand mot
qui surgit). Tout ce qui est dit doit se voir : choisis aussi l'« action » qui correspond au verbe (court → run, montre → point, tombe → fall).
Chaque plan a une « emotion » lisible sur le visage du perso (sourire, larmes « cry », peur, surprise…) : c'est ce qui rend la vidéo vivante.
Intérieurs meublés comme une vraie maison (sofa, tv, rug, frame, window, bookshelf, table + pancakes/plate/mug…) ;
extérieurs avec de la profondeur (plusieurs maisons, sapins, lampadaires, voitures, bus) ; « weather » = snow si l'histoire se passe en hiver.
Modèles de personnages disponibles :
{models}"""


def _sanitize_show(v: Any) -> Optional[Dict[str, Any]]:
    """Objet / mot qui illustre la phrase du plan (apparaît pendant ce plan seulement)."""
    if not isinstance(v, dict):
        return None
    kind = str(v.get("kind") or "").strip().lower()
    text = re.sub(r"\s+", " ", str(v.get("text") or "")).strip().upper()[:24]
    if kind not in PROP_KINDS and kind != "text":
        kind = "text" if text else ""
    if not kind or (kind == "text" and not text):
        return None
    return {"kind": kind, "text": text, "color": _hex(v.get("color"))}


def _sanitize(raw: Dict[str, Any], n_shots: int) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    out: Dict[str, Any] = {
        "time_of_day": raw.get("time_of_day") if raw.get("time_of_day") in ("day", "sunset", "night") else "day",
        "weather": raw.get("weather") if raw.get("weather") in WEATHERS else "none",
        "palette": {k: _hex((raw.get("palette") or {}).get(k)) for k in ("sky", "ground", "accent")},
        "characters": [],
        "locations": [],
        "shots": [],
    }
    for c in (raw.get("characters") or [])[:5]:
        if not isinstance(c, dict):
            continue
        cid = re.sub(r"[^a-z0-9_]", "", str(c.get("id") or "").lower())[:24] or f"p{len(out['characters'])}"
        try:
            scale = max(0.5, min(1.6, float(c.get("scale", 1.0) or 1.0)))
        except (TypeError, ValueError):
            scale = 1.0
        out["characters"].append({
            "id": cid, "name": str(c.get("name") or cid)[:30],
            "model": c.get("model") if c.get("model") in CHAR_MODELS else "villageois_01",
            "shirt": _hex(c.get("shirt")), "pants": _hex(c.get("pants")),
            "hat": _hex(c.get("hat")) or "none", "hair": _hex(c.get("hair")), "scale": scale,
            # styles dessinés (2D × 3D, Explainer) : teint, coiffure et accessoire lisibles
            "skin": _hex(c.get("skin")),
            "hair_style": c.get("hair_style") if c.get("hair_style") in ("short", "long", "wig", "bald") else "short",
            "accessory": c.get("accessory") if c.get("accessory") in ("glasses", "apron", "none") else "none",
        })
    for L in (raw.get("locations") or [])[:5]:
        if not isinstance(L, dict):
            continue
        lid = re.sub(r"[^a-z0-9_]", "", str(L.get("id") or "").lower())[:24] or f"l{len(out['locations'])}"
        props = []
        for p in (L.get("props") or [])[:14]:
            if isinstance(p, dict) and p.get("kind") in PROP_KINDS:
                try:
                    cnt = max(1, min(6, int(p.get("count", 1) or 1)))
                except (TypeError, ValueError):
                    cnt = 1
                props.append({"kind": p["kind"], "count": cnt, "color": _hex(p.get("color")), "text": str(p.get("text") or "")[:24]})
        out["locations"].append({
            "id": lid, "type": L.get("type") if L.get("type") in LOCATION_TYPES else "street",
            "ground": _hex(L.get("ground")), "wall": _hex(L.get("wall")),
            "sign_text": str(L.get("sign_text") or "")[:24], "props": props,
            "time_of_day": L.get("time_of_day") if L.get("time_of_day") in ("day", "sunset", "night") else None,
        })
    if not out["characters"] or not out["locations"]:
        return None
    loc_ids = [L["id"] for L in out["locations"]]
    char_ids = [c["id"] for c in out["characters"]]
    given = {}
    for s in (raw.get("shots") or []):
        if isinstance(s, dict):
            try:
                given[int(s.get("i"))] = s
            except (TypeError, ValueError):
                continue
    prev_cam = ""
    for i in range(n_shots):
        s = given.get(i, {})
        cam = s.get("camera") if s.get("camera") in CAMERAS else ("wide" if i == 0 else ["medium", "close", "wide", "low"][i % 4])
        if cam == prev_cam:
            cam = "medium" if cam != "medium" else "close"
        prev_cam = cam
        focus = s.get("focus") if s.get("focus") in char_ids else char_ids[0]
        others = [o for o in (s.get("others") or []) if o in char_ids and o != focus][:3]
        out["shots"].append({
            "i": i, "location": s.get("location") if s.get("location") in loc_ids else loc_ids[min(i * len(loc_ids) // max(1, n_shots), len(loc_ids) - 1)],
            "camera": cam, "focus": focus, "others": others,
            "action": s.get("action") if s.get("action") in ACTIONS else "idle",
            "emotion": s.get("emotion") if s.get("emotion") in EMOTIONS else "neutral",
            "show": _sanitize_show(s.get("show")),
        })
    return out


_KW_LOC = (
    (("école", "ecole", "classe", "prof"), "school"), (("hôpital", "hopital", "urgence", "médecin"), "hospital"),
    (("bureau", "patron", "travail"), "office"), (("magasin", "boutique", "caisse", "acheter"), "shop"),
    (("marché", "marche"), "market"), (("chambre", "lit", "dormir"), "room"), (("maison", "cuisine", "salon"), "house"),
    (("forêt", "foret", "bois"), "forest"), (("parc", "jardin"), "park"), (("plage", "mer"), "beach"),
    (("lac", "glace"), "lake"), (("espace", "lune", "étoile"), "space"), (("scène", "spectacle"), "stage"),
    (("riche", "tour", "haut", "étage"), "vertical_city"), (("ville", "immeuble"), "city"), (("village",), "village"),
    (("rue", "route"), "street"),
)


_KW_EMO = (
    (("pleur", "larme", "sanglot"), "cry"), (("peur", "terrifi", "effray", "cri", "hurl", "monstre"), "scared"),
    (("triste", "seul", "mort", "perdu", "manque", "jamais revu"), "sad"), (("colère", "colere", "furieux", "énerv"), "angry"),
    (("soudain", "choc", "incroyable", "découvr", "decouvr", "réalis", "comprend"), "surprised"),
    (("rire", "souri", "heureux", "joie", "adore", "blague", "content"), "happy"),
)
_KW_SNOW = ("neige", "hiver", "glace", "gel", "noël", "noel", "flocon", "sapin")


def emotion_for_text(text: str) -> str:
    low = (text or "").lower()
    return next((emo for kws, emo in _KW_EMO if any(k in low for k in kws)), "neutral")


def heuristic_spec(script: Dict[str, Any], plan: Dict[str, Any], style: str) -> Dict[str, Any]:
    """Décor déduit du storyboard et du texte quand l'IA n'est pas disponible."""
    shots = plan.get("shots") or [{"index": 0, "desc": ""}]
    text = (script.get("full_spoken_script") or "").lower()
    types: List[str] = []
    per_shot: List[str] = []
    for s in shots:
        d = f"{s.get('desc', '')}".lower()
        t = next((lt for kws, lt in _KW_LOC if any(k in d for k in kws)), "")
        per_shot.append(t)
        if t and t not in types:
            types.append(t)
    if not types:
        types = [next((lt for kws, lt in _KW_LOC if any(k in text for k in kws)), "vertical_city" if style == "flat_vector" else "village")]
        if len(types) < 2:
            types.append("house" if types[0] != "house" else "street")
    types = types[:4]
    dark = plan.get("mood") in ("dark", "tension")
    palettes = {
        "flat_vector": {"sky": "#FF9E6B", "ground": "#7BD389", "accent": "#FFD23F"},
        "paper2d": {"sky": "#9CCBEF" if not dark else "#1F2A44", "ground": "#DDE3EA", "accent": "#FFC861"},
        "roblox": {"sky": "#4DA3FF" if not dark else "#14213D", "ground": "#5DBB63", "accent": "#FFE14D"},
        "explainer2d": {"sky": "#DCEBF5", "ground": "#E2C9A6", "accent": "#D9406E"},
    }
    raw = {
        "time_of_day": "night" if dark else "day",
        "weather": "snow" if any(k in text for k in _KW_SNOW) else "none",
        "palette": palettes.get(style, palettes["roblox"]),
        "characters": [{"id": "hero", "model": "villageois_10" if " elle " in f" {text} " else "villageois_01",
                        "shirt": "#FF7A1A", "pants": "#2E3A4F", "hair": "#3B2A20"},
                       {"id": "proche", "model": "villageois_06" if any(k in text for k in ("grand", "papi", "mamie", "vieux")) else "villageois_03",
                        "shirt": "#F7C548", "pants": "#6B4E3D", "hat": "#FF6FA8", "scale": 0.9}],
        "locations": [{"id": f"l{i}", "type": t} for i, t in enumerate(types)],
        "shots": [],
    }
    for i, s in enumerate(shots):
        loc_type = per_shot[i] or types[min(i * len(types) // len(shots), len(types) - 1)]
        raw["shots"].append({"i": i, "location": f"l{types.index(loc_type)}" if loc_type in types else "l0",
                             "camera": "drone" if i == 0 else ["medium", "face", "wide", "back", "close", "low", "medium", "high"][i % 8],
                             "focus": "hero", "others": ["proche"] if i % 3 == 1 else [],
                             "action": "walk" if i % 4 == 0 else "idle",
                             "emotion": emotion_for_text(str(s.get("desc") or "") + " " + str(s.get("text") or ""))})
    return _sanitize(raw, len(shots)) or {}


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    txt = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt)
    if m:
        txt = m.group(1)
    try:
        return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
    except Exception:
        return None


def design_scene(
    script: Dict[str, Any],
    plan: Dict[str, Any],
    style: str = "roblox",
    engine: str = "claude",
    model: Optional[str] = None,
    words: Optional[List[Dict[str, Any]]] = None,
    da_hint: str = "",
) -> Dict[str, Any]:
    """Décor de la vidéo, décrit par l'IA choisie ; repli sur le storyboard si besoin. Ajoute `_source`."""
    n = len(plan.get("shots") or []) or 1
    prompt = build_prompt(script, plan, style, words, da_hint)
    raw = ""
    try:
        if (engine or "claude") == "antigravity":
            from core.antigravity_bridge import AntigravityBridge
            raw = AntigravityBridge.query(prompt, model=model, timeout=240)
        else:
            from core.claude_bridge import ClaudeBridge
            raw = ClaudeBridge.query(prompt, action="scene_design")
    except Exception as e:
        print(f"⚠️ Décor IA indisponible ({e}) : décor déduit du storyboard.")
    spec = _sanitize(_parse_json(raw) or {}, n) if raw else None
    if spec:
        spec["_source"] = "ia"
        return spec
    spec = heuristic_spec(script, plan, style)
    spec["_source"] = "storyboard"
    return spec
