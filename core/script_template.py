import re
from typing import Tuple

from core.style_plugins import duration_to_word_range

VIDEO_SCRIPT_TEMPLATE = """# TEMPLATE DE SCRIPT VIDÉO (6 sections obligatoires)

Remplace TOUS les crochets `[ ]` par du vrai contenu complet. Ne laisse aucun crochet vide ni `...`.

## 1. Fiche projet
| Champ | Valeur |
|---|---|
| Titre | [Titre] |
| Idée en une phrase | [Ce qui se passe, en une phrase] |
| Durée totale | [Ex. 1:00] |
| Genre et ton | [Horreur, comédie, drame, pub, tuto…] |
| Lieu(x) | [Où se passe l'action] |
| Personnages | [Liste] |
| Narrateur ou voix off | [Oui / non, qui] |
| Émotion que le spectateur doit garder à la fin | [Une émotion] |
| Fin | [Dernière réplique, carte titre, logo, appel à l'action] |

## 2. Personnages
Une ligne par personnage, y compris le narrateur (pour garder la même voix et la même logique émotionnelle d'un bout à l'autre).
| Personnage | Âge et rôle | Voix (timbre, débit, accent) | Façon de parler (registre, tics, mots récurrents) | Émotion au début | Émotion à la fin | Ce qu'il cache ou ne dit pas |
|---|---|---|---|---|---|---|
| [Nom] | [Âge, rôle] | [Timbre, débit, accent] | [Registre, tics] | [Émotion x/5] | [Émotion x/5] | [Secret, peur, désir] |

## 3. Le script
Une ligne par moment de la vidéo, de 2 à 8 secondes. Timing : compter ~2,5 mots/s pour une réplique dite normalement.
Conventions `Qui parle` : `Nom` (à l'écran), `Nom (VO)` (voix off), `Nom (HC)` (hors champ), `Nom (pensée)` (voix intérieure), `—` (personne ne parle).
Conventions `Émotions` (toujours dans cet ordre) : 1) Personnage + émotion, 2) Intensité 1–5, 3) Ce qui se voit (regard, posture, mains, geste), 4) Ce qui s'entend (voix, souffle, silence), 5) Ce qu'il cache si utile.
| Temps | Scène | Action | Qui parle | Texte | Façon de le dire | Émotions | Effets sonores | Musique |
|---|---|---|---|---|---|---|---|---|
| 0:00–0:04 | [Lieu, ambiance, présents] | [Geste par geste] | [Qui parle] | [Réplique exacte] | [Ton, volume, débit, pauses, souffle] | [Nom : émotion x/5 — visible & audible] | [SFX-01 : description courte] | [MUS-01 : début / continue / coupe] |

## 4. Musiques à créer
Une fiche par morceau (`MUS-01`, `MUS-02`…) référencé dans la colonne Musique, avec un prompt prêt à coller dans un générateur de musique.
### MUS-01
| Champ | Valeur |
|---|---|
| Moment | [Début – fin, durée totale] |
| Scènes couvertes | [Lignes du script concernées] |
| Émotion à provoquer | [Ex. malaise qui devient angoisse] |
| Intensité | [Départ x/5 → arrivée x/5] |
| Genre et style | [Ex. ambient sombre, drone, piano minimaliste] |
| Instruments principaux | [Instruments] |
| Textures et sons ajoutés | [Textures] |
| Tempo | [BPM ou « sans pulsation »] |
| Tonalité et couleur | [Majeur, mineur, dissonant…] |
| Rythme | [Régulier, irrégulier, aucun] |
| Entrée | [Fondu lent, attaque nette…] |
| Évolution seconde par seconde | [Ex. 0:00… → 0:15… → 0:45…] |
| Points à synchroniser | [Timecode + action ou réplique] |
| Place par rapport aux voix | [Sous les voix / coupe / remonte] |
| Volume | [Très discret, présent, premier plan] |
| Sortie | [Coupure nette, fondu, silence] |
| Références | [Films, morceaux ou ambiances] |
| Prompt de génération | [Prompt anglais prêt à coller dans un générateur de musique] |

## 5. Effets sonores à créer
D'abord la liste récapitulative de tous les `SFX-xx` (et les `Silence`), puis une fiche détaillée par `SFX-xx`.
| Code | Timecode | Synchronisé avec | Ce qu'on entend | Durée |
|---|---|---|---|---|
| SFX-01 | [0:02] | [Action ou réplique] | [Description courte] | [0,5 s] |

### Fiche SFX-01 (répéter pour chaque SFX-xx)
| Champ | Valeur |
|---|---|
| Timecode exact | [Ex. 0:02,0] |
| Synchronisé avec | [Action ou réplique] |
| Ce qu'on entend | [Description précise] |
| Matière ou source | [Métal, bois, verre, voix, électronique, corps…] |
| Caractère | [Sec, mou, métallique, humide, étouffé, granuleux] |
| Hauteur | [Grave, médium, aigu, qui monte/descend] |
| Attaque | [Brusque, progressive] |
| Fin | [Coupure nette, résonance, écho] |
| Durée | [En secondes] |
| Espace | [Proche, lointain, gauche/droite, pièce vide, extérieur] |
| Réverbération | [Aucune, légère, cathédrale, vide infini] |
| Répétition | [Une fois, en boucle, x fois] |
| Superposition | [Autres sons ou musique simultanés] |
| Volume dans le mix | [Discret, au niveau des voix, devant tout] |
| Émotion et rôle | [Rôle narratif/émotionnel] |
| Prompt de génération | [Prompt anglais prêt à coller dans un générateur SFX] |
"""


def _format_mmss(seconds: int) -> str:
    sec = max(15, int(seconds or 60))
    m, s = divmod(sec, 60)
    return f"{m}:{s:02d}"


def build_script_generation_prompt(
    topic: str,
    target_duration_sec: int = 60,
    da_context: str = "",
) -> Tuple[str, str]:
    """Construit (system_prompt, user_prompt) pour générer un script complet dans le template exact."""
    dur = duration_to_word_range(target_duration_sec)
    mmss = _format_mmss(dur["duration_sec"])
    system_prompt = (
        "Tu es un scénariste et réalisateur vidéo d'élite.\n"
        "Tu DOIS rédiger le script complet en français en suivant STRICTEMENT le template Markdown ci-dessous "
        "(sections 1 à 5 complètes, tableaux propres, zéro crochet `[ ]` laissé vide, zéro commentaire avant ou après le document).\n"
        "Respecte scrupuleusement les conventions d'écriture : timing cohérent jusqu'à la durée totale (~2,5 mots/s pour les répliques), "
        "émotions décrites dans l'ordre (personnage + émotion + intensité /5 + visible + audible), codes SFX-xx et MUS-xx cohérents entre "
        "le tableau 3 et les fiches 4 & 5, et vrais prompts de génération prêts à coller.\n\n"
        + VIDEO_SCRIPT_TEMPLATE
    )
    da_block = f"\nDirection Artistique (DA) à respecter dans les scènes, actions, émotions et sons :\n{da_context[:3500]}\n" if da_context else ""
    user_prompt = (
        f"Idée de l'utilisateur :\n{topic.strip()}\n\n"
        f"Durée totale visée : {mmss} ({dur['duration_sec']} secondes, environ {dur['min_words']} à {dur['max_words']} mots parlés au total, plans de 2 à 8 s).\n"
        f"{da_block}\n"
        "Génère maintenant le script complet en suivant exactement les 5 sections du template."
    )
    return system_prompt, user_prompt


def build_script_refinement_prompt(
    current_script: str,
    instruction: str,
    da_context: str = "",
) -> Tuple[str, str]:
    """Construit (system_prompt, user_prompt) pour remodifier un script existant avec l'IA."""
    system_prompt = (
        "Tu es un scénariste et réalisateur vidéo d'élite.\n"
        "L'utilisateur te donne son script actuel (au format Template de script vidéo en 5 sections) et une consigne de modification.\n"
        "Applique EXACTEMENT la modification demandée (sans rien casser du reste) et renvoie la version mise à jour COMPLÈTE "
        "en conservant exactement le format Markdown du template (sections 1 à 5, tableaux, codes MUS-xx et SFX-xx cohérents).\n"
        "Ne mets aucun blabla avant ou après le script."
    )
    da_block = f"\nDirection Artistique (DA) active :\n{da_context[:2500]}\n" if da_context else ""
    user_prompt = (
        f"Consigne de modification de l'utilisateur :\n{instruction.strip()}\n"
        f"{da_block}\n"
        f"Script actuel à modifier :\n{current_script.strip()}\n\n"
        "Renvoie le script complet modifié dans le même template."
    )
    return system_prompt, user_prompt


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
