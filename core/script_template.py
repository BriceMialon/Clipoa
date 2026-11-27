import json
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from config import STORAGE_DIR
from core.style_plugins import duration_to_word_range

CUSTOM_TEMPLATES_FILE = STORAGE_DIR / "script_templates.json"
_TPL_LOCK = threading.Lock()

VIDEO_SCRIPT_TEMPLATE = """# FORMAT DE SORTIE (ClipRoll lit ces titres et les colonnes du tableau 3 : garde-les tels quels)

Le contenu, lui, est libre : genre, ton, structure, nombre de personnages et longueur viennent de la demande.
Remplace tous les crochets `[ ]` par du vrai contenu. Pas de `...`, pas de commentaire avant ou après le document.

## 1. Fiche projet
| Champ | Valeur |
|---|---|
| Titre | [Titre] |
| Idée en une phrase | [Ce qui se passe, en une phrase] |
| Format choisi | [Ex. conte à la 1re personne, dialogue à deux, tuto face caméra, sketch, pub, liste… et pourquoi en 5 mots] |
| Ton | [Ex. drôle et absurde, tendre, angoissant, pédagogique, énergique] |
| Durée totale | [Ex. 0:45] |
| Langue | [Français, anglais…] |
| Fin | [Comment la vidéo se termine] |

## 2. Personnages
Une ligne par voix entendue, narrateur compris. Ces infos servent à choisir les voix : sois précis sur l'âge, le genre et le timbre.
| Personnage | Âge et genre | Rôle | Voix (timbre, débit, accent) | Façon de parler |
|---|---|---|---|---|
| [Nom] | [Ex. 12 ans, garçon] | [Rôle] | [Ex. aiguë, rapide, accent parisien] | [Registre, tics] |

## 3. Le script
Une ligne par plan de 2 à 4 secondes. Timing : ~2,5 mots/s pour une réplique dite normalement.
`Qui parle` : `Nom` (à l'écran), `Nom (VO)` (voix off), `Nom (HC)` (hors champ), `Nom (pensée)`, `—` (personne). Écris toujours le même nom pour le même personnage.
| Temps | Scène | Action | Qui parle | Texte | Façon de le dire | Émotions | Effets sonores | Musique |
|---|---|---|---|---|---|---|---|---|
| 0:00–0:03 | [Lieu, ambiance, présents] | [Geste par geste] | [Qui parle] | [Réplique exacte] | [Ton, volume, débit, pauses] | [Nom : émotion x/5, ce qui se voit et s'entend] | [Bruitage court ou —] | [Début / continue / coupe] |
"""


def recent_video_titles(limit: int = 12) -> List[str]:
    """Titres des dernières vidéos rendues (pour que l'IA ne refasse pas la même histoire)."""
    from config import RENDERS_DIR
    titles: List[str] = []
    try:
        metas = sorted(RENDERS_DIR.glob("*/metadata.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for mf in metas[: limit * 2]:
            try:
                t = str((json.loads(mf.read_text(encoding="utf-8")).get("script") or {}).get("title") or "").strip()
            except Exception:
                continue
            if t and t not in titles:
                titles.append(t[:90])
            if len(titles) >= limit:
                break
    except Exception:
        pass
    return titles


def first_sentence(text: str) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    m = re.match(r"(.+?[.!?…])(\s|$)", t)
    return (m.group(1) if m else t)[:140]


def opening_signature(text: str, n_words: int = 3) -> str:
    """Les premiers mots d'une accroche, normalisés (« Dans mon village, une… » → « dans mon village »)."""
    words = re.findall(r"[a-zà-ÿœæ0-9]+", str(text or "").lower())
    return " ".join(words[:n_words])


def recent_video_openings(limit: int = 10) -> List[str]:
    """Premières phrases des dernières vidéos rendues (pour ne pas recommencer toujours de la même façon)."""
    from config import RENDERS_DIR
    out: List[str] = []
    try:
        metas = sorted(RENDERS_DIR.glob("*/metadata.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for mf in metas[: limit * 2]:
            try:
                sc = json.loads(mf.read_text(encoding="utf-8")).get("script") or {}
            except Exception:
                continue
            if not isinstance(sc, dict):
                continue
            o = first_sentence(sc.get("hook_spoken") or sc.get("full_spoken_script") or "")
            if o and o not in out:
                out.append(o)
            if len(out) >= limit:
                break
    except Exception:
        pass
    return out


def repeated_opening(text: str, openings: Optional[List[str]] = None) -> str:
    """Renvoie l'accroche récente dont `text` reprend le début (mêmes 3 premiers mots, ou la même tournure
    « dans ma/mon ville/village… ») ; vide si l'accroche est neuve."""
    sig = opening_signature(first_sentence(text))
    if not sig:
        return ""
    openings = recent_video_openings() if openings is None else openings
    fam = _opening_family(sig)
    for o in openings:
        osig = opening_signature(o)
        if osig and (osig == sig or (fam and fam == _opening_family(osig))):
            return o
    return ""


def _opening_family(sig: str) -> str:
    """Tournures voisines comptées comme une seule : « dans ma ville », « dans mon village », « dans cette ville »…"""
    m = re.match(r"(dans|in) (ma|mon|cette|notre|this|my|our) (ville|village|quartier|famille|école|town|city|village|family)", sig)
    return "dans_mon_lieu" if m else ""


def avoid_titles_block(titles: Optional[List[str]], openings: Optional[List[str]] = None) -> str:
    recent = [t.strip() for t in (titles or []) if t and t.strip()][:12]
    if openings is None:
        openings = recent_video_openings()
    opens = [o for o in openings if o][:10]
    out = ""
    if recent:
        out += (
            "\nHistoires déjà faites récemment (NE PAS les refaire, ni leur objet central, ni leur retournement) :\n- "
            + "\n- ".join(recent) + "\n"
        )
    if opens:
        out += (
            "\nPremières phrases des dernières vidéos. La nouvelle accroche ne doit commencer ni par les mêmes mots ni par la même "
            "tournure (pas de « Dans ma ville / mon village… » si c'est déjà là) : elle naît de CE sujet.\n- "
            + "\n- ".join(opens) + "\n"
        )
    return out


def _format_mmss(seconds: int) -> str:
    sec = max(15, int(seconds or 60))
    m, s = divmod(sec, 60)
    return f"{m}:{s:02d}"


def list_script_templates() -> List[Dict[str, Any]]:
    """Liste le template par défaut + les modèles de script personnalisés ajoutés par l'utilisateur."""
    built_in = [{
        "id": "default",
        "name": "Libre (l'IA choisit le format)",
        "builtin": True,
        "content": VIDEO_SCRIPT_TEMPLATE,
    }]
    with _TPL_LOCK:
        if CUSTOM_TEMPLATES_FILE.exists():
            try:
                customs = json.loads(CUSTOM_TEMPLATES_FILE.read_text(encoding="utf-8"))
                if isinstance(customs, list):
                    for c in customs:
                        if isinstance(c, dict) and c.get("id") and c.get("content"):
                            built_in.append({
                                "id": str(c["id"]),
                                "name": str(c.get("name") or "Mon template")[:60],
                                "builtin": False,
                                "content": str(c["content"]),
                                "created_at": c.get("created_at") or "",
                            })
            except Exception:
                pass
    return built_in


def get_script_template_content(template_id: Optional[str]) -> str:
    tid = (template_id or "default").strip()
    if tid and tid != "default":
        for tpl in list_script_templates():
            if tpl["id"] == tid and tpl.get("content"):
                return str(tpl["content"])
    return VIDEO_SCRIPT_TEMPLATE


def save_custom_script_template(name: str, content: str) -> Dict[str, Any]:
    clean_name = (name or "").strip()[:60] or "Mon modèle de script"
    clean_content = (content or "").strip()[:30000]
    if len(clean_content) < 20:
        raise ValueError("Le modèle de script est trop court (minimum 20 caractères).")
    item = {
        "id": f"tpl_{uuid.uuid4().hex[:8]}",
        "name": clean_name,
        "builtin": False,
        "content": clean_content,
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
    }
    with _TPL_LOCK:
        existing: List[Dict[str, Any]] = []
        if CUSTOM_TEMPLATES_FILE.exists():
            try:
                data = json.loads(CUSTOM_TEMPLATES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    existing = data
            except Exception:
                existing = []
        existing.append(item)
        CUSTOM_TEMPLATES_FILE.parent.mkdir(parents=True, exist_ok=True)
        CUSTOM_TEMPLATES_FILE.write_text(json.dumps(existing[-20:], indent=2, ensure_ascii=False), encoding="utf-8")
    return item


def delete_custom_script_template(template_id: str) -> bool:
    tid = (template_id or "").strip()
    if not tid or tid == "default":
        return False
    with _TPL_LOCK:
        if not CUSTOM_TEMPLATES_FILE.exists():
            return False
        try:
            data = json.loads(CUSTOM_TEMPLATES_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return False
            new_data = [x for x in data if x.get("id") != tid]
            if len(new_data) == len(data):
                return False
            CUSTOM_TEMPLATES_FILE.write_text(json.dumps(new_data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception:
            return False


def build_script_generation_prompt(
    topic: str,
    target_duration_sec: int = 60,
    da_context: str = "",
    template_id: Optional[str] = None,
    avoid_titles: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """
    Construit (system_prompt, user_prompt) en s'adaptant automatiquement au template choisi (défaut ou perso).
    `avoid_titles` : titres des vidéos récentes, pour que l'IA ne ressorte pas toujours la même histoire.
    """
    dur = duration_to_word_range(target_duration_sec)
    mmss = _format_mmss(dur["duration_sec"])
    tpl_body = get_script_template_content(template_id)
    is_custom_tpl = bool(template_id and template_id != "default")

    system_prompt = (
        "Tu es un scénariste et réalisateur de vidéos courtes (Shorts, Reels, TikTok).\n"
        "AVANT d'écrire, déduis toi-même de la demande ce qu'il faut produire : le genre (histoire, sketch, dialogue, "
        "tuto, explication, pub, liste, témoignage…), le ton, la structure qui sert le mieux cette idée, le nombre de "
        "personnages (un narrateur seul, un dialogue, une petite troupe) et la personne (je, tu, il). "
        "Ce que l'utilisateur précise (durée, ton, personnages, langue, structure, fin) passe avant tout le reste.\n"
        "Aucune recette imposée : pas de twist, de morale, de question finale ni d'appel à s'abonner si l'idée ne s'y prête pas. "
        "Seules exigences : accrocher dès la première phrase avec ce que la demande a de plus fort (jamais une formule toute "
        "faite comme « Dans ma ville… » : chaque vidéo a sa propre première phrase), parler comme à l'oral, une idée claire par phrase, "
        "et des répliques jouables à l'image.\n"
        "Écris dans la langue de la demande (français par défaut). Rends le document dans le format ci-dessous, sans rien autour.\n"
        "ORIGINALITÉ : l'histoire part de l'idée de l'utilisateur et rien d'autre. Les objets, décors, structures et exemples cités "
        "dans la Direction Artistique sont des exemples de STYLE, pas des sujets ni des plans imposés : n'en reprends un que s'il sert "
        "vraiment cette idée.\n\n"
        + tpl_body
    )
    da_block = f"\nDirection Artistique (DA) à respecter dans les scènes, actions, émotions et sons :\n{da_context[:12000]}\n" if da_context else ""
    avoid_block = avoid_titles_block(avoid_titles)
    extra_note = (
        "Adapte exactement la structure et les colonnes du modèle personnalisé fourni ci-dessus."
        if is_custom_tpl
        else "Remplis les 3 sections du format (fiche, personnages, script plan par plan), sans en ajouter d'autres."
    )
    user_prompt = (
        f"Idée de l'utilisateur :\n{topic.strip()}\n\n"
        f"Durée demandée : {mmss} ({dur['duration_sec']} secondes). La voix lit environ {dur['target_words']} mots dans ce temps : "
        f"écris entre {dur['min_words']} et {dur['max_words']} mots parlés (compte-les), un plan toutes les 2 à 4 s. "
        "La vidéo doit durer ce qui est demandé, ni beaucoup plus court ni plus long.\n"
        f"{da_block}{avoid_block}\n"
        f"{extra_note}"
    )
    return system_prompt, user_prompt


def build_script_refinement_prompt(
    current_script: str,
    instruction: str,
    da_context: str = "",
    template_id: Optional[str] = None,
) -> Tuple[str, str]:
    """Construit (system_prompt, user_prompt) pour remodifier un script existant avec l'IA."""
    system_prompt = (
        "Tu es un scénariste et réalisateur vidéo d'élite.\n"
        "L'utilisateur te donne son script actuel et une consigne de modification.\n"
        "Applique EXACTEMENT la modification demandée (sans casser le reste) et renvoie la version mise à jour COMPLÈTE "
        "en conservant exactement le même format / template Markdown.\n"
        "Ne mets aucun blabla avant ou après le script."
    )
    da_block = f"\nDirection Artistique (DA) active :\n{da_context[:12000]}\n" if da_context else ""
    user_prompt = (
        f"Consigne de modification de l'utilisateur :\n{instruction.strip()}\n"
        f"{da_block}\n"
        f"Script actuel à modifier :\n{current_script.strip()}\n\n"
        "Renvoie le script complet modifié dans le même format."
    )
    return system_prompt, user_prompt


def extract_shots_from_template(markdown_text: str) -> List[Dict[str, Any]]:
    """
    Extrait la liste structurée des plans (Temps, Scène, Action, Texte) depuis la section `3. Le script`
    afin que Blender génère PLUSIEURS plans distincts couvrant toute la vidéo !
    """
    txt = (markdown_text or "").strip()
    if not txt:
        return []
    sec3 = re.search(r"##\s*3\.\s*Le script([\s\S]*?)(?:\n##\s*4\.|\Z)", txt, flags=re.IGNORECASE)
    if not sec3:
        return []
    lines = [ln.strip() for ln in sec3.group(1).splitlines() if ln.strip().startswith("|")]
    if len(lines) < 3:
        return []

    def _parse_ts_sec(s: str) -> float:
        m = re.search(r"(\d+):(\d+(?:[.,]\d+)?)", s or "")
        if not m:
            return -1.0
        return int(m.group(1)) * 60.0 + float(m.group(2).replace(",", "."))

    shots: List[Dict[str, Any]] = []
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) < 5 or all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        t_raw, scene_desc, action_desc, speaker, spoken = cells[0], cells[1], cells[2], cells[3], cells[4]
        parts = re.split(r"[–—\-]+", t_raw)
        start_s = _parse_ts_sec(parts[0]) if parts else -1.0
        end_s = _parse_ts_sec(parts[1]) if len(parts) > 1 else -1.0
        shots.append({
            "time_raw": t_raw,
            "start_s": start_s,
            "end_s": end_s,
            "scene": scene_desc,
            "action": action_desc,
            "speaker": speaker,
            "text": spoken.strip("«»\"' "),
        })
    return shots


def extract_title_from_template(markdown_text: str, fallback: str = "Mon Short") -> str:
    txt = (markdown_text or "").strip()
    m = re.search(r"^\|\s*\*{0,2}Titre\*{0,2}\s*\|\s*([^|\n]+?)\s*\|", txt, flags=re.IGNORECASE | re.MULTILINE)
    if m:
        candidate = m.group(1).strip().strip("*_[]«»\"' ")
        if candidate and candidate.lower() != "titre":
            return candidate[:80]
    return (fallback or "Mon Short").strip()[:80]


def extract_spoken_script_from_template(markdown_text: str) -> str:
    """
    Extrait proprement les répliques parlées de la section `3. Le script` (colonne `Texte`)
    pour la voix off / synthèse vocale. Si ce n'est pas un tableau template, renvoie le texte tel quel.
    """
    txt = (markdown_text or "").strip()
    if not txt:
        return ""

    # Locate section 3 table
    sec3 = re.search(r"##\s*3\.\s*Le script([\s\S]*?)(?:\n##\s*4\.|\Z)", txt, flags=re.IGNORECASE)
    if not sec3:
        return txt

    block = sec3.group(1)
    lines = [ln.strip() for ln in block.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 3:
        return txt

    header_cells = [c.strip().lower() for c in lines[0].strip("|").split("|")]
    text_idx = None
    for i, h in enumerate(header_cells):
        if "texte" in h or "réplique" in h or "replique" in h or "dialogue" in h:
            text_idx = i
            break
    if text_idx is None:
        text_idx = 4  # Standard 9-column template: Temps|Scène|Action|Qui parle|Texte|...

    spoken_parts = []
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) <= text_idx:
            continue
        # Skip separator rows
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        raw_line = cells[text_idx].strip()
        if not raw_line or raw_line in ("—", "-", "–", "...", "…", "[Réplique exacte]", "Aucune", "Aucun", "Silence"):
            continue
        cleaned = raw_line.strip("«»\"' ").strip()
        if cleaned:
            spoken_parts.append(cleaned)

    return " ".join(spoken_parts).strip() if spoken_parts else txt
