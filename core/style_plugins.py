import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from werkzeug.utils import secure_filename

from config import STORAGE_DIR, DEFAULT_THEME, DEFAULT_SUBTITLE_STYLE
from core.settings_store import load_settings, CLAUDE_PLAN_BUDGETS

PLUGINS_DIR = STORAGE_DIR / "plugins"
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
PLUGINS_INDEX_FILE = PLUGINS_DIR / "plugins.json"

_LOCK = threading.Lock()
_SAFE_PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,140}$")

ALLOWED_SHEET_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".glb", ".blend", ".pdf"}
IMAGE_SHEET_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
ALLOWED_SCRIPT_EXTS = {".py", ".js", ".ts", ".sh", ".json", ".txt", ".md"}

MAX_SHEET_BYTES = 25 * 1024 * 1024  # 25 MB per model sheet
REFERENCE_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}
MAX_REFERENCE_VIDEO_BYTES = 300 * 1024 * 1024
# Rendus faits AVANT cette date (epoch) n'illustrent plus le style (moteur refait) : jamais montrés comme exemple
STARTER_LOOK_SINCE: Dict[str, float] = {"2d_monde_3d": 1795627000.0, "explainer_2d": 1795627000.0}
# Vidéos de référence livrées avec Clipoa (choisies par l'éditeur, pas par les utilisateurs) : assets/style_refs/<id>.mp4
STYLE_REFS_DIR = Path(__file__).resolve().parent.parent / "assets" / "style_refs"
MAX_SCRIPT_BYTES = 2 * 1024 * 1024  # 2 MB per script

PLUGIN_GRADIENTS = [
    {"id": "roblox", "label": "3D Roblox (Bleu / Or)", "css": "sp-plug-roblox"},
    {"id": "2d", "label": "2D × 3D (Émeraude / Cyan)", "css": "sp-plug-2d"},
    {"id": "cartoon", "label": "Cartoon (Corail / Ambre)", "css": "sp-plug-cartoon"},
    {"id": "anime", "label": "Anime (Violet / Rose)", "css": "sp-plug-anime"},
    {"id": "cinema", "label": "Cinéma (Charbon / Or)", "css": "sp-plug-cinema"},
    {"id": "custom", "label": "Perso (Indigo / Verre)", "css": "sp-plug-custom"},
]

PLUGIN_CATEGORIES = [
    "3D",
    "2D × 3D",
    "2D",
    "Cartoon",
    "Anime",
    "Cinéma",
    "Perso",
]

SCRIPT_LANGUAGES = [
    {"id": "python", "label": "Python / Blender (.py)", "ext": ".py"},
    {"id": "javascript", "label": "JavaScript / Three.js (.js)", "ext": ".js"},
    {"id": "shell", "label": "FFmpeg / Shell (.sh)", "ext": ".sh"},
    {"id": "json", "label": "Config JSON (.json)", "ext": ".json"},
    {"id": "prompt", "label": "Instructions (.txt)", "ext": ".txt"},
]

SHEET_ROLES = [
    {"id": "personnages", "label": "Personnages"},
    {"id": "decors", "label": "Décors"},
    {"id": "expressions", "label": "Expressions"},
    {"id": "palette", "label": "Palette"},
    {"id": "reference", "label": "Aperçu"},
]

STYLE_BIBLE_ROBLOX_3D = """# STYLE BIBLE — « 3D Roblox » : Dans ma ville (pop) & Conte en blocs (mélancolie)

> **À l'IA qui lit ce fichier :** tu reçois après ce document un **script oral** (ou une idée). Produis le script / découpage plan par plan, prompts, sous-titres et montage **exactement dans cette direction artistique**.
> Ordre : §0 choisir la variante → §1 règles d'or → §2–§6 DA → §7 découpage → §8 prompts → §9 montage → §10 checklist.

## 0. CHOISIR LA VARIANTE (une seule par vidéo)
- **A — « Roblox pop »** : script drôle, absurde, mème, répétitif, énergique (réf. @synelite1).
- **B — « Conte en blocs mélancolique »** : script émouvant, deuil, règles étranges, secret, twist final (réf. @fusedintheblankfr). Des personnages tout mignons portent une histoire grave : ton doux, intime, jamais gore. La peur vient des règles et de la révélation ; on finit sur une émotion (larmes, apaisement), pas sur un choc violent. Récit plus long et posé (60 à 140 s).

## 1. RÈGLES D'OR (communes A et B)
1. **Personnages = avatars Roblox classiques (R6)** : tête cylindrique arrondie (A) ou cube adouci voxel (B), corps en blocs, bras et jambes rectangulaires, **visage = décalcomanie 2D plate** (2 points noirs pour les yeux, trait de bouche simple). Jamais de doigts, jamais de nez, jamais d'anatomie réaliste.
2. **Décors = 3D low-poly propre**, objets simples et lisibles, aucune texture photoréaliste.
3. **Format 9:16**, 1080×1920, 30 fps.
4. **Plans très courts** : 1–1,5 s en A, 2–3 s en B. Caméra presque toujours en mouvement.
5. **Ouverture obligatoire** : « Dans ma ville / In this town, [règle absurde ou surnaturelle] » dans les 2 premières secondes, sur un plan de ville.
6. **Narrateur à la 1re personne**, qui fait exception à la règle (A) ou en est victime (B).
7. **Chaque phrase est montrée littéralement** à l'image avec **panneaux 3D lisibles** dans le décor (BAKERY, MATH TEST, PARTY HOUSE, CLOSED, TOWN MEETING…).
8. **Un objet/gimmick récurrent** dans presque tous les plans (A : ballon de basket orange ; B : neige, miroirs couverts, écran blanc, lumière sous la glace).

## 2. PERSONNAGES & ACCESSOIRES
- Plastique lisse mat (A) ou aplats légèrement facettés, ombres franches (B). Animations volontairement raides façon jeu vidéo.
- Émotions uniquement par le décal : `^ ^` joyeux, sourcils froncés, bouche en vague, larme bleue en goutte (B).
- 1 accessoire fort par perso, jamais changé (ex A : bonnet bleu roi + sweat étoilé, maire haut-de-forme + écharpe rouge, mamie lunettes rondes, boulanger toque ; ex B : chapka sombre + manteau vert sapin, grand-père casquette plate + écharpe rouge, petite sœur bonnet rose + doudoune jaune).

## 3. DÉCORS & LUMIÈRE
- **A — Roblox pop** : banlieue américaine low-poly, rue goudronnée ligne blanche pointillée, maisons pastel, gratte-ciels pastel au loin, ciel bleu vif `#4DA3FF` + nuages cartoon, Party House violette `#6B4FC9` disco (rose `#FF5FA2`, cyan `#3DE0E0`, jaune `#FFE14D`).
- **B — Conte en blocs** : palette **« chaud dedans / froid dehors »**.
  - Intérieur : papier peint crème rayé `#E9DFC6`, parquet `#8A5232`, plinthes blanches, fauteuil bordeaux `#8E1F2A`, télé, table, lumière chaude `#FFD9A0`.
  - Extérieur de jour : neige `#F1F3F6`, ciel gris-lilas `#C9C3D3`, sapins `#2F4A3A`, maisons rouge suédois `#9B2C2C` et blanc.
  - Extérieur de nuit : bleu nuit `#1E2A44`, neige bleutée `#B9C6DE`, lampadaires et fenêtres chauds.
  - Final : sous la glace `#1F5D7E`, faisceaux de lumière blanche. **Flashback vérité en noir et blanc** (désaturation progressive quand la vérité approche).
  - Lumière douce de soleil d'hiver, ombres douces au sol, contre-jours dans les portes. Pas de contours dessinés.

## 4. SOUS-TITRES
- **A (Pop)** : 1 mot à la fois, Montserrat SemiBold ~52 px, blanc contour noir 2 px, centre écran (~58 % hauteur, y=1110), onomatopées en MAJ.
- **B (Mélancolie)** : groupes de mots coupés par proposition, Montserrat Bold, **blanc** contour noir fin + ombre légère, juste sous le centre, ponctuation conservée. **Aucune couleur sur les mots-clés**, aucun emoji, aucune animation « pop », coupe sèche. Pas de cartons.

## 5. CAMÉRA, MONTAGE & DÉCOUPAGE
- Plan d'ouverture survol/drone ou travelling rue. Alternance plan large → plan moyen → gros plan visage décal. Cuts francs (fondu au noir uniquement en fin de B).
- **A** : rythme mème (1–1,5 s), caméra vlog, fin en boucle.
- **B** : rythme conte (2–4 s, 3 s en moyenne), ouverture aérienne sur le village puis on resserre ; alternance plans larges / moyens / **très gros plans de visages** (tête cube qui remplit l'écran, larme bleue `#8EC9F0` qui coule) sur chaque émotion ; plans de détail sur les objets-règles (télé, miroir, nourriture, porte) ; plans de dos qui suivent un perso qui marche, plongées sur les traces de pas ; push-in lents, coupes franches, **coupe au noir avant le plan final** ; final en contre-plongée vers une lumière puis gros plan apaisé, yeux fermés.
- **Son B** : voix off au « je », calme, un peu brisée, proche du micro, ~2,8 mots/s avec de vrais silences (0,5–1 s) avant les phrases fortes. Piano / boîte à musique et nappes douces, bas ; la musique **s'arrête juste avant la révélation** et revient plus aérienne à la fin. Bruitages discrets : vent, pas dans la neige, porte, grésillement de télé, craquement de glace, sons étouffés sous l'eau.

## 6. PHRASES-ANCRES PROMPTS
- **Style A** : `Roblox game screenshot style, classic R6 blocky avatars with rounded cylindrical heads, flat 2D decal faces (two black dot eyes, simple line mouth), smooth matte plastic materials, bright saturated colors, clean low-poly American suburb, vivid blue sky with big puffy cartoon clouds, soft global illumination, vertical 9:16, no text except in-world signs`
- **Style B** : `blocky low-poly 3D animation in the style of a Roblox story, cube-shaped heads with flat 2D decal faces (black dot eyes, small eyebrows, pink blush), rectangular block bodies, muted desaturated colors, snowy Scandinavian village with red wooden houses and low-poly pine trees, soft cinematic lighting, gentle film grain, slight vignette, shallow depth of field, vertical 9:16, no text except in-world signs`
- **Image-to-video** : `Animate this frame in Roblox game animation style: stiff blocky limb movement, {action}. Camera {mouvement}. Face decals stay flat and unchanged. No morphing, no realistic anatomy, no fingers.`
- **Voix** : A = jeune blasé pince-sans-rire (~3,2 mots/s) ; B = jeune douce posée mélancolique (~2,5 mots/s) avec silences avant révélations.
"""

NARRATIVE_RULES_ROBLOX_3D = """Structure « Dans ma ville » (variante A pop) :
1. Hook (0–2 s) : « Dans ma ville, [règle absurde ou surnaturelle]. Sauf moi. »
2. Origine en 1 phrase.
3. Litanie d'exemples (4 à 7 persos-types), 1 plan chacun.
4. Conséquence sur la ville / premier cas vécu.
5. Bascule personnelle → retournement en boucle comique.
6. Chute en boucle qui répond à la première phrase.

Structure « Conte en blocs » (variante B mélancolie) — narration au « je » (enfant ou jeune adulte), passé composé et imparfait, phrases courtes avec répétitions émotives (« j'ai essayé, j'ai vraiment essayé ») :
1. Accroche-règle (0–7 s) : une loi étrange de « ma ville » ou de « ma famille », posée calmement.
2. Premier souvenir et règles : la première fois qu'on a vu le phénomène, puis 3 ou 4 règles concrètes et visuelles (objet à cacher ou à allumer, interdit émotionnel) et la conséquence si on les enfreint.
3. Le drame : un accident ou une perte, raconté pudiquement, avec de la culpabilité.
4. La journée de retour : on applique les règles, petits détails tendres (repas préféré, programme télé). « Pendant une journée, tout était normal. »
5. La séparation : la marche finale, on se lâche la main, l'interdit est brisé, on se retourne.
6. Les indices retournés : 2 ou 3 détails semés plus tôt relus autrement, en phrases de 2 à 4 mots.
7. Le twist : phrase sèche précédée d'un silence (ex. c'était le narrateur qui était mort).
8. L'apaisement : une image de lumière et une dernière phrase douce. Pas de CTA agressif, au plus une question très courte."""

STYLE_BIBLE_2D_MONDE_3D = """# STYLE BIBLE — « Stickman 2.5D » : persos 2D dans un monde 3D (format TikTok / Shorts)

> **Règles chiffrées (33 000 images de la chaîne d'origine analysées) :** quelque chose bouge sur 96 % des images ; la caméra bouge
> sur ~85 % des images et ne coupe JAMAIS sèchement (un seul vol continu) ; l'image change toutes les ~2,1 s et un nouvel élément
> apparaît chaque seconde. Chaque proposition du script = une action du perso + un mouvement de caméra (si une phrase ne peut pas
> être jouée, réécris-la). Le perso fait exactement ce que dit le narrateur, sur le mot. Chaque nom du script a son objet à l'image.
> 3 persos ou plus à l'écran au moins un quart du temps (quelqu'un réagit toujours). Le fond est toujours vivant (fumée, oiseaux,
> eau, foule). Seuls les persos sont 2D ; tout le reste est en vraie 3D avec un contour encre épais.

## 0. LE STICKMAN
Tête ovale « haricot » BLANC PUR (jamais teintée par la lumière), yeux = deux points noirs, sourcils très expressifs, bouche qui
bouge quand il parle, pas de nez ni de joues ; petit torse coloré (pull, gilet, salopette) ; bras et jambes = traits d'encre fins ;
un accessoire signature par perso (bonnet, chapeau, lunettes). L'expression change toutes les 0,3 à 0,8 s (regard, clignement).


> **À l'IA qui lit ce fichier :** transforme le script oral (ou l'idée) en vidéo verticale respectant **exactement** ce contraste : personnages dessin animé 2D plats à contours épais posés dans un décor 3D low-poly / semi-réaliste.

## 1. RÈGLES D'OR
1. **Personnages = dessin animé 2D plat** (contours épais `#2B1B2F` / `#1E1B3A`, couleurs unies sans ombrage, gros yeux ronds blancs à pupille noire, joues roses ovales, bras/jambes bâtons fins) **posés dans un décor 3D** (rendu jeu indé low-poly / toy town ou village français brumeux). Jamais de personnage 3D réaliste, jamais de décor 2D plat.
2. **Format 9:16**, 1080×1920, 30 fps.
3. **Un plan toutes les 2 à 3 secondes**, caméra jamais fixe (drone lent, push-in, travelling, orbit).
4. **Sous-titres 1 à 3 mots**, blancs `#FFFFFF` à contour noir 4 px, sans fond ni emoji, centrés à ~70 % de hauteur.
5. **Narration à la 1re personne**, voix off unique calme et posée (~2,6 mots/s), phrases courtes de 4 à 10 mots.
6. **Objet-clé / magique récurrent** (orbe/fiole dorée lumineuse `#FFC861`, allumette, cordes…) qui revient dans tous les moments-clés.
7. **Contraste lumière** : extérieur froid (bleu-gris `#8C9BB0`, neige ou brume) vs intérieur chaud (orange `#D9A066`, feu, flamme) ou nuit bleu profond (`#1F2A44`).

## 2. PERSONNAGES 2D
- Tête ronde/ovale ~1/3 de la hauteur, grands yeux ronds blancs contour épais noir, joues roses blush, sourcils très expressifs, pas de nez, corps trapèze simple, longues jambes bâtons.
- Peaux non réalistes assumées (vert menthe `#8EDDC4` / cyan `#8FD8D2`, beige, rose). 1 accessoire + 1 couleur par perso (ex : bonnet à pompon orange `#F28C38`, sweat jaune `#F2B33D`, manteau bleu marine `#2E3F66`, haut-de-forme violet `#5B3A6E`).
- Variante horreur/suspense : villageois aux yeux pâles sans pupille, créature 2D sombre très grande et fine couverte d'yeux.

## 3. DÉCORS 3D & LUMIÈRE
- Ville d'hiver 3D low-poly (maisons bois bleu ardoise/gris, neige, pavés, étals guinguette, cheminées d'usine, lac gelé) OU village français 3D brumeux (façades ocre/bleu-gris, volets bois, cordes sur poteaux).
- Intérieurs chaleureux (fauteuil rouge, cheminée, chambre d'enfant). Bloom doux sur les lumières, léger flou de profondeur et grain fin.

## 4. PHRASES-ANCRES PROMPTS
- **Style global** : `2D flat cartoon characters composited into a stylized low-poly 3D environment, hand-drawn characters with thick dark plum outlines (#2B1B2F), flat colors, no shading, huge round white eyes with small black pupils, pink blush ovals on cheeks, thin stick-like arms and very long thin legs, oversized round heads; the background is a cozy 3D game-engine toy town render, soft depth of field, gentle bloom, light film grain, vertical 9:16 composition, no text overlay`
- **Image-to-video** : `Animate this frame. {mouvement caméra}. Characters keep their flat 2D cartoon look and thick outlines, minimal cut-out puppet motion: {action}. Falling snow or subtle mist. No morphing, no style change, no text.`
"""

NARRATIVE_RULES_2D_MONDE_3D = """Structure Stickman — conte / suspense (phrases courtes de 4 à 10 mots, 1re personne) :
1. Hook-concept (0–3 s) : règle étrange du monde (« Dans ma ville, tout le monde… sauf moi »).
2. Exemples concrets / règles du monde (1 plan par règle).
3. Bascule personnelle + lien affectif / objet-clé.
4. Montée de tension / perte jour après jour.
5. Révélation / twist court (≤ 8 mots) qui réutilise les règles posées au début.
6. Chute émotionnelle qui boucle avec le début.
Rythme Stickman : narration dense (~3,5 mots/s, presque sans pause), chaque phrase jouable à l'image (une action + un objet par nom)."""

STYLE_BIBLE_FETE_EN_FOLIE = """# STYLE GUIDE — « La Tour des Riches » (flat vector motion story, TikTok 9:16)

> **À l'IA qui lit ce fichier :** tu vas recevoir un script oral (voix off) ou une idée. Produis le script / découpage plan par plan, prompts, sous-titres et montage **exactement** dans ce style. Ne réinvente pas la DA : respecte les règles chiffrées.

## 1. L'ADN
Histoire à la 1re personne racontée d'une traite, illustrée en **dessin animé vectoriel plat, ultra-saturé et propre**, avec **un nouveau plan à chaque phrase** (≈ 2–3 s), **un seul mot affiché à la fois au centre de l'écran**, et des **éléments d'interface TikTok intégrés au décor** (commentaires, bouton S'abonner, likes).

## 2. FORMAT TECHNIQUE
- Ratio 9:16, 1080×1920, 30 fps. Durée cible 40–90 s.
- Rythme : 1 plan par phrase, durée moyenne **2,3 s** (min 0,8 s, max 4 s). Aucun silence, pas d'intro, pas de logo, pas d'écran titre.
- Zone sûre : rien d'important dans les 12 % du bas ni les 8 % du haut. Personnage principal entre 35 % et 85 % de la hauteur.
- Musique : aucune musique marquée (ou nappe très basse), la voix porte tout (~3 mots/s).

## 3. DIRECTION ARTISTIQUE VISUELLE
- **Flat vector 2D** : aplats de couleur, **pas de contour noir** (ou contours de la même teinte plus foncée), ombres en un seul aplat plus sombre, quelques reflets blancs arrondis. Jamais de texture réaliste, jamais de 3D Pixar ni d'anime.
- **Bloc style à coller dans CHAQUE prompt image** :
  `flat vector illustration, clean 2D motion-design style, bold saturated colors, no black outlines, single-tone cel shadows, simple geometric shapes, smooth gradients only in the sky, explainer-animation look, vertical 9:16 composition, crisp edges, no text, no watermark`
- **Palette** : ciel jour `#1EA7FF → #7FD0FF`, ciel riche/soir `#FF3FA4 → #FF9A3C`, ciel nuit/espace `#2A0E6B → #7B2FF7`, magenta `#FF3FA4`, violet `#8A4DFF`, bleu `#2F8CFF`, vert `#2BD46B`, jaune or `#FFC91F`, sweat héros orange `#FF7A1A` (ombre `#E0550A`), sol décharge `#9A5521`, blanc `#F4F9FF`. Au moins 3 couleurs saturées par plan, jamais de plan gris.
- **Métaphore verticale (hauteur = richesse)** :
  1. En bas : décharge marron, cabanes en planches orange, pneus, frigos cassés, TV fêlée, fumées vertes.
  2. Gens normaux : petits immeubles colorés (orange, rose) avec château d'eau.
  3. Aisés / millionnaires : maisons pastel posées sur des plateformes au sommet de tours très hautes et fines (violet, bleu, vert), palmiers.
  4. Milliardaires : île flottante dans l'espace, piscine en cascade, hélicoptère, voiture rose, **lune géante** à côté.
  - Rayon de lumière orange/doré vertical symbole de l'ascension.
- **Personnages** : proportions « explainer », tête ovale, **yeux = 2 points noirs**, joues rosées rondes, pas de doigts détaillés. Héros identique dans tous les plans : sweat à capuche + pantalon **orange vif**, patch rapiécé sur la jambe, cheveux bruns mi-longs. Générer une fiche personnage (character sheet) en référence pour tous les plans.

## 4. GRAMMAIRE DES PLANS & ANIMATION
- Alterner 8 types (jamais 2 fois de suite) : `EST` (large vertical), `TILT` (panoramique vertical le long des tours), `HERO` (héros en pied face caméra), `CU` (gros plan buste/visage), `POV` (mains/plateau/échelle), `TOP` (vue plongeante/tunnel), `STAGE` (scène de théâtre/marionnette), `UI` (élément d'interface TikTok géant).
- **Chaque plan bouge** : push-in 100 → 108 %, tilt vertical, travelling, animation puppet simple, éléments en boucle (fumées, nuages, étoiles, confettis, traits jaunes de pop). Coupes franches (1–2 whip-pan ou morph max, jamais de fondu au noir).
- **Prompt image-to-video** : `[mouvement caméra] + [action simple du personnage] + "flat 2D vector animation, keep the exact art style, smooth motion, no morphing of the character, no new objects"`.

## 5. SOUS-TITRES « UN MOT À LA FOIS » & UI INTÉGRÉE
- **1 seul mot à la fois**, centré (x=50 %, y=48 %), ~76 px, **TOUT EN MAJUSCULES**, pop-in 85 → 100 % en 0,08 s, sans boîte noire. Style qui change à chaque mot (pool : gras arrondi shadow, condensé italique marine contour blanc, remplissage texturé décor, lettres multicolores, glitch arc-en-ciel, 3D extrudé, dessiné main vert) — jamais 2 fois de suite.
- **UI TikTok dessinée dans le décor** (au moins 1 tous les 4–5 plans + obligatoire dans les 3 derniers) : carte commentaire TikTok brillante, bulles likées avec cœur rose + couronne, bouton « + S'abonner » rose / « ✓ Abonné » jaune, champ commentaire vide, étiquettes prix (« 0 € », « 10 € »), compteurs d'étage.

## 6. PROCÉDURE & CHECKLIST
- Découper en segments de 0,8–4 s → produire la shot list JSON (`id, start, end, voice, shot_type, world_level, image_prompt, motion_prompt, ui_element`) → fiche personnage → images → animation I2V → voix off + timestamps mot à mot → montage + sous-titres 1 mot.
- Refuser tout rendu 3D réaliste/Pixar/anime, tout contour noir épais, tout plan > 4 s ou fixe, toute phrase complète en sous-titre.
"""

NARRATIVE_RULES_FETE_EN_FOLIE = """Structure « vie pilotée par les commentaires » (1re personne, présent, phrases courtes, ~3 mots/s) :
1. Hook (0–4 s) : la règle du monde en une phrase (« Dans cette ville, plus t'es riche, plus tu vis haut. ») → plan EST/TILT.
2. Situation du héros (4–10 s) : où il vit, ce qu'il n'a pas → HERO, décharge.
3. Contrat spectateur (10–20 s) : abonnés / commentaires = progression → UI + STAGE.
4. Action / montée (20–70 s) : gradation verticale du décor, phrases courtes et sensorielles, 1 plan par phrase.
5. Cliffhanger + CTA (5–8 dernières s) : question ouverte + « le commentaire le plus/moins liké décide » → CU + UI commentaire vide + bouton S'abonner."""

STYLE_BIBLE_EXPLAINER_2D = r"""# STYLE BIBLE — « Explainer 2D » (dessin animé illustré chaleureux, Shorts / Reels / TikTok 9:16)

> **À l'IA qui lit ce fichier :** tu reçois un script oral ou une idée (une notion, un métier, une astuce, une anecdote d'histoire, une marque locale). Reproduis exactement ce STYLE avec l'histoire de l'utilisateur. Ne copie jamais les personnages, noms ou textes des vidéos de référence.

## 1. L'ADN
Petite histoire explicative de 20 à 50 s racontée par une voix off chaleureuse, illustrée comme un **dessin animé de livre jeunesse** : décors riches et cosy, un héros attachant en gros plan, de petites animations simples. Contenu simple, rythme régulier, un format qu'on peut décliner en série (même héros, même décor, nouvelle astuce).

## 2. FORMAT
- 9:16, 1080×1920. Plans de 2 à 5 s.
- **Sous-titres** par groupes de 2-3 mots, blancs à contour brun foncé, le mot prononcé en **jaune crème** `#FFE08A`, sous le centre.
- **Carton-titre** en haut à chaque moment clé : petit panneau crème `#FFF4DC` aux coins arrondis, texte brun foncé (une question « Ta chantilly ne monte pas ? », une date « 1770 », un nom). Gros chiffres possibles en blanc à contour orange.

## 3. DIRECTION ARTISTIQUE
- **Contours épais brun foncé** `#3B2A20` sur TOUT (personnages, meubles, objets), aplats de couleur avec une ombre douce d'un ton plus foncé, aucun dégradé photo.
- Palette chaude : murs crème / jaune pâle `#F6E3B4`, bois miel `#C98A4B`, bleu ardoise `#4E6E8E` (meubles, placards), vert sapin `#3F7F5F`, rouge doux `#D9534F`, peau pêche `#F7D2B6`, joues roses.
- **Décors détaillés et cosy** vus de face : cuisine (carrelage, étagère à bocaux, placards), bureau (bibliothèque pleine de livres colorés, fenêtre avec lune ou soleil, bougie, encrier), salon, boutique, atelier, salle de classe. Objets du sujet bien visibles (le fouet et le saladier, le dessin sur la feuille…).
- **Personnages chibi** : grosse tête ronde (près de la moitié du corps), grands yeux blancs à pupille brun foncé et reflet, sourcils expressifs, petit nez, bouche qui sourit, joues roses, coiffure simple (mèche, frange, perruque d'époque), accessoires lisibles (lunettes rondes, tablier, perruque, chapeau). Corps court, mains rondes. UN geste par plan : fouetter, montrer, écrire, saluer.
- Vue plongeante possible sur une table (feuille, outils) pour les étapes concrètes.

## 4. CAMÉRA & MONTAGE
- Caméra de face, héros cadré à la taille ou en gros plan (sa tête dans le tiers haut-milieu). Léger zoom avant pendant le plan, glissé latéral quand on change de lieu.
- Fin : le héros sourit ou salue + une phrase-chute ou un appel à l'action d'une ligne.

## 5. SON
- Voix off unique, chaleureuse, tutoiement ou vouvoiement selon le sujet. Musique douce (piano, ukulélé, clochettes) assez basse, petits « pop » quand un élément apparaît.

## 6. PHRASES-ANCRES (prompts)
- `cozy 2D cartoon illustration, children's book style, thick dark brown outlines, warm flat colors with soft cel shading, detailed front-view interior, chibi character with big round head, big white eyes, rosy cheeks, round glasses, vertical 9:16, cream rounded title sign at the top, white subtitles with dark outline`
"""

NARRATIVE_RULES_EXPLAINER_2D = r"""Structure « explainer de marque » (vouvoiement, phrases courtes et factuelles, ~2,7 mots/s) :
1. Accroche (0-4 s) : un objet ou une situation personnifiée, avec une pointe d'humour (« Cette rose a peut-être fait plus de route que vous cette semaine. »).
2. Le problème en chiffre (4-11 s) : un chiffre-choc écrit en grand, puis d'où vient le problème (carte, trajet).
3. Le contraste (11-21 s) : « Pourtant… » + une énumération rythmée (saison par saison, étape par étape), une étiquette géante par élément.
4. La solution (vers la moitié) : la marque / le héros entre en scène et fait la chose différemment.
5. La preuve concrète (un délai, un chiffre, un geste du métier).
6. La conséquence pour le spectateur (« Alors votre bouquet change avec les mois. ») + une phrase-chute courte.
7. Carton final : nom + promesse en une ligne + appel à l'action simple (« Passez voir celles de la semaine »)."""

STYLE_BIBLE_ROBLOX_CINE = r"""# STYLE BIBLE — « Roblox 3D Ciné » (qualité cinéma, Shorts 9:16)

## 1. L'ADN
Une fable racontée au « je » ou par un conteur passionné, mise en images dans un monde 3D en blocs façon Roblox (R6),
avec un rendu de cinéma : vraie lumière, ombres de contact, lumière de contour, brume, bloom la nuit, étalonnage doux.
Les personnages sont VIVANTS : ils clignent des yeux, respirent, bougent la bouche quand ils parlent, changent d'expression.

## 2. Format
- 1080x1920, 30 i/s. 60 à 90 s. Un plan toutes les 2 à 3 s (1,5 à 4 s), 20 à 35 plans.
- Sous-titres : UN mot à la fois, Montserrat Black blanc à contour noir, juste sous le centre ; mots-clés en MAJUSCULES
  Luckiest Guy jaune #FFE600 (idée clé), rouge #E74C3C (perte, danger), vert #2ECC71 (gain, solution). Notes en haut.

## 3. Image
- Monde low-poly en blocs arrondis, matières mates, couleurs franches mais douces. Pas de texture photo.
- Visages en texture : neutre, sourire, rire, inquiet, choqué, colère, cri. L'émotion se lit à chaque plan.
- Éclairages : jour, couvert, heure dorée, nuit (fenêtres et lampadaires qui brillent), brouillard, « frisson »
  (brume froide et contre-jour, pour le moment glaçant). Flashback en sépia ou noir et blanc. Flash blanc à la révélation.
- Caméra : plan aérien d'ouverture, plans taille, gros plans visage (menton à 60 % de la hauteur), plongées, contre-plongées,
  plans d'objet. Travelling lent permanent (3-8 %), jamais deux cadrages identiques de suite, tremblement sur les chocs.
- Ce que dit la phrase est MONTRÉ : un objet, un panneau, un écran, un geste.

## 4. Son
- Voix conteur, posée, avec de vrais silences avant les phrases fortes.
- Musique générée sous la voix (-17 dB, ducking), coupée juste avant le twist. ≤ 20 bruitages, jamais stridents.

## 5. À éviter
- Caméra dans un objet, tête coupée en haut du cadre, personnages qui se traversent, image noire.
- Logo, son ou avatar Roblox réels. Le requin mascotte n'apparaît que si l'histoire le demande.
"""


STARTER_PLUGINS: List[Dict[str, Any]] = [
    {
        "id": "roblox_3d",
        "name": "3D Roblox",
        "category": "3D",
        "icon": "🧱",
        "gradient": "roblox",
        "tagline": "Avatars R6 en blocs : « Dans ma ville » drôle ou conte mélancolique.",
        "da_prompt": STYLE_BIBLE_ROBLOX_3D,
        "narrative_rules": NARRATIVE_RULES_ROBLOX_3D,
        "render_mode": "blender3d",
        "theme": "cyber_grid",
        "subtitle_style": "clean_white",
        "est_time_sec": 65,
        "est_time_label": "~1m05",
        "script_language": "python",
        "script_filename": "",
        "script_content": "",
        "model_sheets": [
            {
                "filename": "roblox_3d.jpg",
                "original_name": "roblox_3d.jpg",
                "role": "reference",
                "uploaded_at": "2026-11-25 01:15",
            }
        ],
        "starter": True,
    },
    {
        "id": "2d_monde_3d",
        "name": "Stickman",
        "category": "Stickman 2.5D",
        "icon": "🎨",
        "gradient": "2d",
        "tagline": "Stickmen 2D à tête de haricot dans un monde 3D à contours encre.",
        "da_prompt": STYLE_BIBLE_2D_MONDE_3D,
        "narrative_rules": NARRATIVE_RULES_2D_MONDE_3D,
        "render_mode": "blender3d",
        "theme": "neon_pulse",
        "subtitle_style": "clean_white",
        "est_time_sec": 65,
        "est_time_label": "~1m05",
        "script_language": "python",
        "script_filename": "",
        "script_content": "",
        "model_sheets": [
            {
                "filename": "2d_monde_3d.jpg",
                "original_name": "2d_monde_3d.jpg",
                "role": "reference",
                "uploaded_at": "2026-11-25 01:15",
            }
        ],
        "starter": True,
    },
    {
        "id": "fete_en_folie",
        "name": "Fête en folie",
        "category": "2D",
        "icon": "🎉",
        "gradient": "cartoon",
        "tagline": "Flat vector 2D saturé, tour verticale et UI TikTok.",
        "da_prompt": STYLE_BIBLE_FETE_EN_FOLIE,
        "narrative_rules": NARRATIVE_RULES_FETE_EN_FOLIE,
        "render_mode": "motion",
        "theme": "cinema_gold",
        "subtitle_style": "submagic_yellow",
        "est_time_sec": 60,
        "est_time_label": "~1 min",
        "script_language": "python",
        "script_filename": "",
        "script_content": "",
        "model_sheets": [
            {
                "filename": "fete_en_folie.jpg",
                "original_name": "fete_en_folie.jpg",
                "role": "reference",
                "uploaded_at": "2026-11-25 01:15",
            }
        ],
        "starter": True,
    },
    {
        "id": "explainer_2d",
        "name": "Explainer 2D pastel",
        "category": "2D",
        "icon": "🌷",
        "gradient": "cartoon",
        "tagline": "Dessin animé illustré chaleureux : héros chibi, décors cosy, contours épais.",
        "da_prompt": STYLE_BIBLE_EXPLAINER_2D,
        "narrative_rules": NARRATIVE_RULES_EXPLAINER_2D,
        "render_mode": "blender3d",
        "theme": "pop_flat",
        "subtitle_style": "warm_cream",
        "est_time_sec": 70,
        "est_time_label": "~1m10",
        "script_language": "python",
        "script_filename": "",
        "script_content": "",
        "model_sheets": [
            {
                "filename": "explainer_2d.jpg",
                "original_name": "explainer_2d.jpg",
                "role": "reference",
                "uploaded_at": "2026-11-25 11:20",
            }
        ],
        "starter": True,
    },
    {
        "id": "roblox_cine",
        "name": "Roblox 3D Ciné (haute qualité)",
        "category": "3D",
        "icon": "🎬",
        "gradient": "roblox",
        "tagline": "Qualité cinéma : vraie lumière, visages vivants, 1080p 30 i/s. Rendu long et plus de tokens.",
        "da_prompt": STYLE_BIBLE_ROBLOX_CINE,
        "narrative_rules": NARRATIVE_RULES_ROBLOX_3D,
        "render_mode": "blender3d",
        "theme": "cinema_gold",
        "subtitle_style": "submagic_yellow",
        "est_time_sec": 2400,
        "est_time_label": "~20 à 60 min",
        "heavy": True,
        "script_language": "python",
        "script_filename": "",
        "script_content": "",
        "model_sheets": [
            {
                "filename": "roblox_cine.jpg",
                "original_name": "roblox_cine.jpg",
                "role": "reference",
                "uploaded_at": "2026-11-25 14:00",
            }
        ],
        "starter": True,
    },
]


# Réglages de production par style (méthode Clipoa) — appliqués au montage, au son et à Blender.
# Valeurs par défaut des styles livrés ; un style peut les surcharger via son champ « production ».
STARTER_PRODUCTION: Dict[str, Dict[str, Any]] = {
    # DA : plans 1-1,5 s (variante pop) à 2-3 s (mélancolie), caméra toujours en mouvement
    "roblox_3d": {"shot_min_s": 1.2, "shot_max_s": 3.5, "keyword_colors": False, "character_style": "r6", "visual_style": "roblox"},
    # DA : un plan toutes les 2-3 s ; sous-titres 1-3 mots BLANCS à contour noir (pas de couleurs)
    # Stickman (réf. 2.5D, 33 000 images) : image qui change ~toutes les 2,1 s, ~8 bruitages / 10 s, souffle sur chaque mouvement de caméra
    "2d_monde_3d": {"shot_min_s": 1.6, "shot_max_s": 2.8, "keyword_colors": False, "caption_mode": "two_words", "character_style": "flat2d", "visual_style": "paper2d",
                    "sfx_max": 40, "whoosh_min_gap_s": 2.0, "sfx_repeat_gap_s": 1.2},
    # DA : un plan par phrase (~2,3 s), UN seul mot à la fois, pas de musique marquée (nappe très basse)
    "fete_en_folie": {"shot_min_s": 1.2, "shot_max_s": 3.0, "caption_mode": "one_word", "music_db": -22.0, "mood": "upbeat", "visual_style": "flat_vector"},
    # DA : plans plus longs (l'image s'anime pendant la phrase), PAS de sous-titres, grandes étiquettes, musique douce
    "explainer_2d": {"shot_min_s": 2.0, "shot_max_s": 5.0, "caption_mode": "chunk", "keyword_colors": False, "note_look": "card", "music_db": -18.0, "mood": "calm", "visual_style": "explainer2d", "note_color": "#3B2A20"},
    # Qualité cinéma : moteur three.js ciné (rendu long, plus de tokens), un mot à la fois, mots-clés colorés
    "roblox_cine": {"shot_min_s": 1.5, "shot_max_s": 4.0, "caption_mode": "one_word", "music_db": -17.0, "character_style": "r6", "visual_style": "cine3d"},
}

_PRODUCTION_SPEC: Dict[str, Any] = {
    "mood": ("enum", ("dark", "tension", "upbeat", "calm")),
    "music_db": ("float", (-40.0, 0.0)),
    "shot_min_s": ("float", (0.6, 6.0)),
    "shot_max_s": ("float", (1.0, 12.0)),
    "sfx_max": ("int", (0, 40)),
    "whoosh_min_gap_s": ("float", (2.0, 60.0)),
    "sfx_repeat_gap_s": ("float", (0.5, 20.0)),
    "music_cut_before_twist_s": ("float", (0.0, 3.0)),
    "caption_mode": ("enum", ("chunk", "one_word", "two_words", "none")),
    "keyword_colors": ("bool", None),
    "character_style": ("enum", ("r6", "flat2d")),
    "visual_style": ("enum", ("roblox", "paper2d", "flat_vector", "explainer2d", "cine3d", "custom")),
    "fallback_style": ("enum", ("roblox", "paper2d", "flat_vector", "explainer2d")),
    "note_color": ("hex", None),
    "note_look": ("enum", ("text", "card")),
    # copie d'une vidéo : couleurs et lumière de l'original imposées au décor, compteurs permanents en haut (« ALTITUDE : 5 M »)
    "palette": ("palette", None),
    "time_of_day": ("enum", ("day", "sunset", "night")),
    "hud": ("bool", None),
    "hud_color": ("hex", None),
    "caption_look": ("enum", ("", "cine")),
}


def sanitize_production(raw: Any) -> Dict[str, Any]:
    """Ne garde que les réglages de production connus, bornés et typés."""
    out: Dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for key, (kind, rng) in _PRODUCTION_SPEC.items():
        if key not in raw or raw[key] in (None, ""):
            continue
        val = raw[key]
        try:
            if kind == "palette":
                if isinstance(val, dict):
                    pal = {}
                    for pk in ("sky", "ground", "accent"):
                        pv = str(val.get(pk) or "").strip().lstrip("#")
                        if re.match(r"^[0-9a-fA-F]{6}$", pv):
                            pal[pk] = "#" + pv.upper()
                    if pal:
                        out[key] = pal
            elif kind == "hex":
                v = str(val).strip().lstrip("#")
                if re.match(r"^[0-9a-fA-F]{6}$", v):
                    out[key] = "#" + v.upper()
            elif kind == "enum":
                v = str(val).strip().lower()
                if v in rng:
                    out[key] = v
            elif kind == "bool":
                out[key] = val if isinstance(val, bool) else str(val).strip().lower() in ("1", "true", "yes", "on", "oui")
            elif kind == "int":
                out[key] = int(max(rng[0], min(rng[1], int(float(val)))))
            else:
                out[key] = float(max(rng[0], min(rng[1], float(val))))
        except (TypeError, ValueError):
            continue
    if "shot_min_s" in out and "shot_max_s" in out and out["shot_max_s"] < out["shot_min_s"] + 0.4:
        out["shot_max_s"] = out["shot_min_s"] + 0.4
    return out


REMOVED_STARTERS_FILE = PLUGINS_DIR / "removed_starters.json"

# style livré -> {champ: (ancienne valeur livrée, nouvelle valeur)} (migration douce des installations existantes)
STARTER_DEFAULT_UPDATES: Dict[str, Dict[str, Any]] = {
    # références 2D × 3D : sous-titres blancs à contour noir (plus de mot actif cyan)
    "2d_monde_3d": {"subtitle_style": ("cyber_cyan", "clean_white"),
                    "da_prompt": ("prefix:# STYLE BIBLE — « Conte cartoon 2D dans un monde 3D »", STYLE_BIBLE_2D_MONDE_3D),
                    "narrative_rules": ("prefix:Structure conte / suspense", NARRATIVE_RULES_2D_MONDE_3D),
                    # renommé « Stickman » (réf. pipeline 2.5D stickman, 33 000 images analysées)
                    "name": ("2D × Monde 3D", "Stickman"),
                    "category": ("2D × 3D", "Stickman 2.5D"),
                    "tagline": ("Persos cartoon 2D plats dans un décor 3D.", "Stickmen 2D à tête de haricot dans un monde 3D à contours encre.")},
    # 3D Roblox fusionné avec « Conte Blocs Mélancolique » (un seul style, le meilleur des deux)
    "roblox_3d": {"subtitle_style": ("submagic_yellow", "clean_white"),
                  "tagline": ("Avatars R6 en blocs dans un monde 3D low-poly.", "Avatars R6 en blocs : « Dans ma ville » drôle ou conte mélancolique."),
                  "da_prompt": ("prefix:# STYLE BIBLE — « In this town / Dans ma ville »", STYLE_BIBLE_ROBLOX_3D),
                  "narrative_rules": ("prefix:Structure « In this town / Dans ma ville »", NARRATIVE_RULES_ROBLOX_3D)},
    # références @rosoai (cuisine, savant 1770) : sous-titres blancs + mot prononcé jaune crème, DA illustrée chaleureuse
    "explainer_2d": {"subtitle_style": ("shortcrew_red", "warm_cream"),
                     "tagline": ("Dessin animé vectoriel pastel vu de face, grandes étiquettes, voix posée.", "Dessin animé illustré chaleureux : héros chibi, décors cosy, contours épais."),
                     "da_prompt": ("prefix:# STYLE BIBLE — « Explainer 2D pastel »", STYLE_BIBLE_EXPLAINER_2D)},
}


def _clean_reference_url(url: Any) -> str:
    u = str(url or "").strip()[:500]
    return u if re.match(r"^https?://[^\s<>\"']+$", u) else ""


def _REMOVED_STARTERS(_data: Any = None) -> set:
    """Styles livrés que l'utilisateur a supprimés : on ne les rajoute jamais d'office."""
    try:
        return set(json.loads(REMOVED_STARTERS_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _slugify_id(name: str) -> str:
    raw = (name or "").strip().lower()
    raw = re.sub(r"[àáâãäå]", "a", raw)
    raw = re.sub(r"[èéêë]", "e", raw)
    raw = re.sub(r"[ìíîï]", "i", raw)
    raw = re.sub(r"[òóôõö]", "o", raw)
    raw = re.sub(r"[ùúûü]", "u", raw)
    raw = re.sub(r"[ç]", "c", raw)
    slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")[:40]
    if not slug or len(slug) < 2:
        slug = f"plugin_{uuid.uuid4().hex[:6]}"
    elif not slug[0].isalnum():
        slug = f"p_{slug}"
    return slug


def is_valid_plugin_id(plugin_id: str) -> bool:
    return bool(plugin_id and _SAFE_PLUGIN_ID_RE.match(plugin_id) and ".." not in plugin_id)


def _format_duration_label(sec: int) -> str:
    sec = max(15, int(sec or 60))
    if sec < 60:
        return f"~{sec}s"
    mins, rem = divmod(sec, 60)
    if rem == 0:
        return f"~{mins} min"
    return f"~{mins}m{rem:02d}"


def _format_tokens_label(tokens: int) -> str:
    if tokens >= 1000:
        return f"~{tokens / 1000.0:.1f}k tokens".replace(".", ",")
    return f"~{tokens} tokens"


def duration_to_word_range(duration_sec: int = 60) -> Dict[str, int]:
    """Calcule la fourchette de mots parlés et le nombre de plans pour une durée cible (en secondes)."""
    sec = max(15, min(180, int(duration_sec or 60)))
    center = int(round(sec * 2.65))
    low = max(30, int(round(center * 0.90)))
    high = max(low + 15, int(round(center * 1.08)))
    plans_min = max(6, int(round(sec / 3.0)))
    plans_max = max(plans_min + 3, int(round(sec / 2.2)))
    return {
        "duration_sec": sec,
        "min_words": low,
        "max_words": high,
        "plans_min": plans_min,
        "plans_max": plans_max,
    }


def estimate_plugin_cost_and_time(raw: Dict[str, Any], sheets_count: int = 0, duration_sec: int = 60) -> Dict[str, Any]:
    """
    Calcule le temps de fabrication estimé et le coût en tokens (Claude + Gemini)
    sur la base d'une vidéo moyenne de 1 minute (60s) par défaut, avec scaling selon `duration_sec`.
    """
    da_len = len(str(raw.get("da_prompt") or ""))
    narr_len = len(str(raw.get("narrative_rules") or ""))
    script_len = min(1800, len(str(raw.get("script_content") or "")))
    render_mode = str(raw.get("render_mode") or "motion")
    scale = max(0.4, min(3.0, float(duration_sec or 60) / 60.0))

    input_chars = 2400 + da_len + narr_len + script_len + (sheets_count * 70)
    est_input_tokens = max(500, int(round(input_chars / 3.8)))

    if da_len >= 3000:
        base_out_1m = 1450
    elif da_len >= 800:
        base_out_1m = 1100
    else:
        base_out_1m = 800
    est_output_tokens = int(round(base_out_1m * (0.4 + 0.6 * scale)))

    if ((raw.get("production") or {}).get("visual_style") or STARTER_PRODUCTION.get(str(raw.get("id") or ""), {}).get("visual_style")) == "cine3d":
        # l'IA écrit les plans 3D en code (≈ 30 Ko) puis les corrige après la planche de contrôle
        est_input_tokens += 26000
        est_output_tokens += 18000
    est_total_tokens = est_input_tokens + est_output_tokens

    try:
        settings = load_settings()
        claude_cfg = settings.get("claude", {})
        c_model = (claude_cfg.get("model") or "opus").lower()
        c_plan = claude_cfg.get("plan") or "pro"
    except Exception:
        c_model = "opus"
        c_plan = "pro"

    pricing_map = {
        "opus": (15.0, 75.0),
        "sonnet": (3.0, 15.0),
        "haiku": (0.8, 4.0),
    }
    p_in, p_out = pricing_map.get(c_model, (15.0, 75.0))
    est_claude_usd = round((est_input_tokens * p_in + est_output_tokens * p_out) / 1_000_000.0, 3)

    plan_budget = float(CLAUDE_PLAN_BUDGETS.get(c_plan, CLAUDE_PLAN_BUDGETS["pro"])["budget_5h_usd"])
    est_quota_pct = min(100.0, round((est_claude_usd / max(1.0, plan_budget)) * 100.0, 1))

    custom_sec = int(raw.get("est_time_sec") or 0)
    if custom_sec > 0:
        base_sec_1m = custom_sec
    else:
        base_sec_1m = 45
        if render_mode == "blender3d":
            base_sec_1m = 135
        elif render_mode == "ai_video":
            base_sec_1m = 105
        elif render_mode == "custom_script":
            base_sec_1m = 90
        if da_len >= 3000:
            base_sec_1m += 20
        elif da_len >= 800:
            base_sec_1m += 10

    est_time_sec = int(round(base_sec_1m * (0.45 + 0.55 * scale)))
    custom_lbl = str(raw.get("est_time_label") or "").strip()
    est_time_label = custom_lbl if (custom_lbl and duration_sec == 60) else _format_duration_label(est_time_sec)

    return {
        "est_base_duration_sec": 60,
        "est_input_tokens": est_input_tokens,
        "est_output_tokens": est_output_tokens,
        "est_total_tokens": est_total_tokens,
        "est_tokens_label": _format_tokens_label(est_total_tokens),
        "est_claude_usd": est_claude_usd,
        "est_claude_quota_pct": est_quota_pct,
        "est_claude_model": c_model,
        "est_time_sec": est_time_sec,
        "est_time_label": est_time_label,
    }


def _compute_plugin_view(raw: Dict[str, Any], include_script_body: bool = False) -> Dict[str, Any]:
    pid = raw.get("id", "")
    sheets = []
    cover_url = ""
    sheets_dir = PLUGINS_DIR / pid / "sheets"
    for s in raw.get("model_sheets") or []:
        if not isinstance(s, dict):
            continue
        fname = str(s.get("filename") or "")
        if not fname or not _SAFE_FILENAME_RE.match(fname):
            continue
        fpath = sheets_dir / fname
        if not fpath.exists():
            continue
        ext = fpath.suffix.lower()
        is_img = ext in IMAGE_SHEET_EXTS
        url = f"/api/plugins/{pid}/sheets/{fname}"
        if is_img and not cover_url:
            cover_url = url
        sheets.append({
            "filename": fname,
            "original_name": s.get("original_name") or fname,
            "role": s.get("role") or "reference",
            "is_image": is_img,
            "ext": ext,
            "size_kb": round(fpath.stat().st_size / 1024, 1),
            "url": url,
            "uploaded_at": s.get("uploaded_at") or "",
        })

    script_content = str(raw.get("script_content") or "")
    script_filename = str(raw.get("script_filename") or "")
    da_prompt = str(raw.get("da_prompt") or "")
    narrative_rules = str(raw.get("narrative_rules") or "")

    has_sheets = len(sheets) > 0
    has_script = bool(script_content.strip() or script_filename)
    has_da = bool(da_prompt.strip())

    if has_da and (has_sheets or has_script or len(da_prompt) >= 500):
        status = "ready"
        status_label = "Prêt"
    elif has_da or has_sheets or has_script:
        status = "partial"
        status_label = "En cours"
    else:
        status = "template"
        status_label = "À préparer"

    grad = raw.get("gradient") or "custom"
    grad_css = next((g["css"] for g in PLUGIN_GRADIENTS if g["id"] == grad), "sp-plug-custom")
    metrics = estimate_plugin_cost_and_time(raw, sheets_count=len(sheets))

    out = {
        "id": pid,
        "name": str(raw.get("name") or "Nouveau Plugin")[:50],
        "category": str(raw.get("category") or "Perso")[:40],
        "icon": str(raw.get("icon") or "🧩")[:8],
        "gradient": grad,
        "gradient_css": grad_css,
        "tagline": str(raw.get("tagline") or "")[:200],
        "da_prompt": da_prompt,
        "narrative_rules": narrative_rules,
        "render_mode": raw.get("render_mode") if raw.get("render_mode") in ("motion", "blender3d", "ai_video", "broll", "custom_script") else "motion",
        "theme": str(raw.get("theme") or DEFAULT_THEME),
        "subtitle_style": str(raw.get("subtitle_style") or DEFAULT_SUBTITLE_STYLE),
        "script_language": str(raw.get("script_language") or "python"),
        "script_filename": script_filename,
        "script_lines": len(script_content.splitlines()) if script_content.strip() else 0,
        "model_sheets": sheets,
        "sheets_count": len(sheets),
        "has_sheets": has_sheets,
        "has_script": has_script,
        "has_da": has_da,
        "status": status,
        "status_label": status_label,
        "cover_url": cover_url,
        "starter": bool(raw.get("starter", False)),
        "reference_url": str(raw.get("reference_url") or ""),
        "hidden": bool(raw.get("hidden")),
        "has_reference_video": bool(raw.get("reference_video")),
        "production": {**STARTER_PRODUCTION.get(pid, {}), **sanitize_production(raw.get("production"))},
        "heavy": bool(raw.get("heavy")) or ({**STARTER_PRODUCTION.get(pid, {}), **sanitize_production(raw.get("production"))}.get("visual_style") == "cine3d"),
        "created_at": raw.get("created_at") or "",
        "updated_at": raw.get("updated_at") or "",
        **metrics,
    }
    if include_script_body:
        out["script_content"] = script_content
    return out


class StylePluginStore:
    """
    Stockage & orchestration des Plugins de Style (Direction Artistique) de Clipoa.
    """

    @classmethod
    def _load_raw_unlocked(cls) -> List[Dict[str, Any]]:
        if not PLUGINS_INDEX_FILE.exists():
            now = time.strftime("%Y-%m-%d %H:%M")
            seeded = []
            for p in STARTER_PLUGINS:
                item = json.loads(json.dumps(p))
                item["created_at"] = now
                item["updated_at"] = now
                seeded.append(item)
            _atomic_write_json(PLUGINS_INDEX_FILE, seeded)
            return seeded
        try:
            with open(PLUGINS_INDEX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data = data if isinstance(data, list) else []
        except Exception:
            return []
        # Ajoute les nouveaux styles livrés avec Clipoa (ex. Explainer 2D) sans toucher aux styles existants
        known = {p.get("id") for p in data if isinstance(p, dict)}
        added = False
        for sp in STARTER_PLUGINS:
            if sp["id"] not in known and sp["id"] not in _REMOVED_STARTERS(data):
                item = json.loads(json.dumps(sp))
                item["created_at"] = item["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
                data.append(item)
                added = True
                # vignette livrée avec Clipoa (assets/style_covers/<id>.jpg)
                try:
                    cover = Path(__file__).resolve().parent.parent / "assets" / "style_covers" / f"{sp['id']}.jpg"
                    dest = PLUGINS_DIR / sp["id"] / "sheets" / f"{sp['id']}.jpg"
                    if cover.exists() and not dest.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(cover, dest)
                except Exception:
                    pass
        # Réglages livrés corrigés depuis : appliqués seulement si l'utilisateur a gardé l'ancienne valeur livrée
        for p in data:
            if not isinstance(p, dict):
                continue
            for key, (old_val, new_val) in STARTER_DEFAULT_UPDATES.get(p.get("id"), {}).items():
                cur = p.get(key)
                if cur == old_val or (isinstance(old_val, str) and old_val.startswith("prefix:") and isinstance(cur, str) and cur.startswith(old_val[7:])):
                    p[key] = new_val
                    added = True
        if added:
            try:
                _atomic_write_json(PLUGINS_INDEX_FILE, data)
            except Exception:
                pass
        return data

    @classmethod
    def _save_raw_unlocked(cls, items: List[Dict[str, Any]]) -> None:
        _atomic_write_json(PLUGINS_INDEX_FILE, items)

    @classmethod
    def list_plugins(cls, include_script_body: bool = False) -> List[Dict[str, Any]]:
        with _LOCK:
            items = cls._load_raw_unlocked()
        # styles « copiés d'une vidéo » (lien collé dans la Fabrique) : internes, jamais proposés dans la liste
        return [_compute_plugin_view(p, include_script_body=include_script_body) for p in items if not p.get("hidden")]

    @classmethod
    def set_hidden(cls, plugin_id: str, hidden: bool = True) -> None:
        with _LOCK:
            items = cls._load_raw_unlocked()
            for p in items:
                if p.get("id") == plugin_id:
                    p["hidden"] = bool(hidden)
            cls._save_raw_unlocked(items)

    @classmethod
    def get_plugin(cls, plugin_id: str, include_script_body: bool = True) -> Optional[Dict[str, Any]]:
        if not is_valid_plugin_id(plugin_id):
            return None
        with _LOCK:
            items = cls._load_raw_unlocked()
            for p in items:
                if p.get("id") == plugin_id:
                    return _compute_plugin_view(p, include_script_body=include_script_body)
        return None

    @classmethod
    def create_plugin(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Donne un nom à ton plugin de style.")

        now = time.strftime("%Y-%m-%d %H:%M")
        with _LOCK:
            items = cls._load_raw_unlocked()
            existing_ids = {p.get("id") for p in items}
            base_id = _slugify_id(payload.get("id") or name)
            pid = base_id
            suffix = 2
            while pid in existing_ids or not is_valid_plugin_id(pid):
                pid = f"{base_id[:50]}_{suffix}"
                suffix += 1

            script_content = str(payload.get("script_content") or "")
            if len(script_content.encode("utf-8")) > MAX_SCRIPT_BYTES:
                raise ValueError("Script trop volumineux (max 2 Mo).")

            script_lang = str(payload.get("script_language") or "python").strip().lower()
            valid_langs = {s["id"]: s["ext"] for s in SCRIPT_LANGUAGES}
            if script_lang not in valid_langs:
                script_lang = "python"

            script_fname = secure_filename(str(payload.get("script_filename") or "").strip())
            if script_content.strip() and not script_fname:
                script_fname = f"{pid}{valid_langs[script_lang]}"

            grad = str(payload.get("gradient") or "custom").strip().lower()
            if grad not in {g["id"] for g in PLUGIN_GRADIENTS}:
                grad = "custom"

            render_mode = str(payload.get("render_mode") or "motion").strip().lower()
            if render_mode not in ("motion", "blender3d", "ai_video", "broll", "custom_script"):
                render_mode = "motion"

            est_time_sec = 0
            try:
                est_time_sec = max(0, min(3600, int(payload.get("est_time_sec") or 0)))
            except (TypeError, ValueError):
                est_time_sec = 0

            new_item: Dict[str, Any] = {
                "id": pid,
                "name": name[:50],
                "category": str(payload.get("category") or "Perso").strip()[:40],
                "icon": str(payload.get("icon") or "🧩").strip()[:8] or "🧩",
                "gradient": grad,
                "tagline": str(payload.get("tagline") or "").strip()[:200],
                "da_prompt": str(payload.get("da_prompt") or "").strip()[:32000],
                "narrative_rules": str(payload.get("narrative_rules") or "").strip()[:8000],
                "render_mode": render_mode,
                "theme": str(payload.get("theme") or DEFAULT_THEME),
                "subtitle_style": str(payload.get("subtitle_style") or DEFAULT_SUBTITLE_STYLE),
                "est_time_sec": est_time_sec,
                "est_time_label": str(payload.get("est_time_label") or "").strip()[:32],
                "production": sanitize_production(payload.get("production")),
                "script_language": script_lang,
                "script_filename": script_fname,
                "script_content": script_content,
                "model_sheets": [],
                "starter": False,
                "created_at": now,
                "updated_at": now,
            }

            (PLUGINS_DIR / pid / "sheets").mkdir(parents=True, exist_ok=True)
            (PLUGINS_DIR / pid / "scripts").mkdir(parents=True, exist_ok=True)
            if script_content.strip() and script_fname:
                (PLUGINS_DIR / pid / "scripts" / script_fname).write_text(script_content, encoding="utf-8")

            items.append(new_item)
            cls._save_raw_unlocked(items)
            return _compute_plugin_view(new_item, include_script_body=True)

    @classmethod
    def update_plugin(cls, plugin_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not is_valid_plugin_id(plugin_id):
            raise ValueError("ID de plugin invalide.")

        with _LOCK:
            items = cls._load_raw_unlocked()
            target = next((p for p in items if p.get("id") == plugin_id), None)
            if not target:
                raise FileNotFoundError("Plugin introuvable.")

            if "name" in payload:
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ValueError("Le nom du plugin ne peut pas être vide.")
                target["name"] = name[:50]
            if "category" in payload:
                target["category"] = str(payload.get("category") or "Perso").strip()[:40]
            if "icon" in payload:
                target["icon"] = str(payload.get("icon") or "🧩").strip()[:8] or "🧩"
            if "gradient" in payload:
                g = str(payload.get("gradient") or "custom").strip().lower()
                if g in {x["id"] for x in PLUGIN_GRADIENTS}:
                    target["gradient"] = g
            if "tagline" in payload:
                target["tagline"] = str(payload.get("tagline") or "").strip()[:200]
            if "da_prompt" in payload:
                target["da_prompt"] = str(payload.get("da_prompt") or "").strip()[:32000]
            if "narrative_rules" in payload:
                target["narrative_rules"] = str(payload.get("narrative_rules") or "").strip()[:8000]
            if "production" in payload:
                target["production"] = sanitize_production(payload.get("production"))
            if "render_mode" in payload:
                rm = str(payload.get("render_mode") or "motion").strip().lower()
                if rm in ("motion", "blender3d", "ai_video", "broll", "custom_script"):
                    target["render_mode"] = rm
            if "reference_url" in payload:
                target["reference_url"] = _clean_reference_url(payload.get("reference_url"))
            if "theme" in payload:
                target["theme"] = str(payload.get("theme") or DEFAULT_THEME)
            if "subtitle_style" in payload:
                target["subtitle_style"] = str(payload.get("subtitle_style") or DEFAULT_SUBTITLE_STYLE)
            if "est_time_sec" in payload:
                try:
                    target["est_time_sec"] = max(0, min(3600, int(payload.get("est_time_sec") or 0)))
                except (TypeError, ValueError):
                    pass
            if "est_time_label" in payload:
                target["est_time_label"] = str(payload.get("est_time_label") or "").strip()[:32]
            if "script_language" in payload:
                sl = str(payload.get("script_language") or "python").strip().lower()
                if sl in {s["id"] for s in SCRIPT_LANGUAGES}:
                    target["script_language"] = sl
            if "script_content" in payload:
                sc = str(payload.get("script_content") or "")
                if len(sc.encode("utf-8")) > MAX_SCRIPT_BYTES:
                    raise ValueError("Script trop volumineux (max 2 Mo).")
                target["script_content"] = sc
                valid_langs = {s["id"]: s["ext"] for s in SCRIPT_LANGUAGES}
                fname = secure_filename(str(payload.get("script_filename") or target.get("script_filename") or "").strip())
                if sc.strip() and not fname:
                    fname = f"{plugin_id}{valid_langs.get(target.get('script_language', 'python'), '.py')}"
                elif not sc.strip():
                    fname = ""
                target["script_filename"] = fname
                scripts_dir = PLUGINS_DIR / plugin_id / "scripts"
                scripts_dir.mkdir(parents=True, exist_ok=True)
                if fname and sc.strip():
                    (scripts_dir / fname).write_text(sc, encoding="utf-8")
            elif "script_filename" in payload:
                target["script_filename"] = secure_filename(str(payload.get("script_filename") or "").strip())

            target["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
            cls._save_raw_unlocked(items)
            return _compute_plugin_view(target, include_script_body=True)

    @classmethod
    def delete_plugin(cls, plugin_id: str) -> bool:
        if not is_valid_plugin_id(plugin_id):
            return False
        with _LOCK:
            items = cls._load_raw_unlocked()
            new_items = [p for p in items if p.get("id") != plugin_id]
            if len(new_items) == len(items):
                return False
            cls._save_raw_unlocked(new_items)
            if any(sp["id"] == plugin_id for sp in STARTER_PLUGINS):
                removed = _REMOVED_STARTERS()
                removed.add(plugin_id)
                _atomic_write_json(REMOVED_STARTERS_FILE, sorted(removed))
        pdir = (PLUGINS_DIR / plugin_id).resolve()
        if pdir.parent == PLUGINS_DIR.resolve() and pdir.exists():
            shutil.rmtree(pdir, ignore_errors=True)
        return True

    @classmethod
    def add_model_sheet(cls, plugin_id: str, file_storage, role: str = "reference") -> Dict[str, Any]:
        if not is_valid_plugin_id(plugin_id):
            raise ValueError("ID de plugin invalide.")
        if not file_storage or not file_storage.filename:
            raise ValueError("Aucun fichier sélectionné.")

        orig_name = Path(file_storage.filename).name
        safe = secure_filename(orig_name) or "planche.png"
        ext = Path(safe).suffix.lower()
        if ext not in ALLOWED_SHEET_EXTS:
            raise ValueError(f"Format non supporté ({ext}). Formats acceptés : PNG, JPG, WEBP, SVG, GLB, BLEND, PDF.")

        clean_role = role if role in {r["id"] for r in SHEET_ROLES} else "reference"
        stored_name = f"{int(time.time())}_{uuid.uuid4().hex[:5]}_{safe}"
        if not _SAFE_FILENAME_RE.match(stored_name):
            stored_name = f"sheet_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"

        with _LOCK:
            items = cls._load_raw_unlocked()
            target = next((p for p in items if p.get("id") == plugin_id), None)
            if not target:
                raise FileNotFoundError("Plugin introuvable.")

            sheets_dir = PLUGINS_DIR / plugin_id / "sheets"
            sheets_dir.mkdir(parents=True, exist_ok=True)
            dest = sheets_dir / stored_name
            file_storage.save(str(dest))
            if dest.stat().st_size > MAX_SHEET_BYTES:
                dest.unlink(missing_ok=True)
                raise ValueError("Fichier trop lourd (maximum 25 Mo par planche).")

            sheets = target.setdefault("model_sheets", [])
            sheets.append({
                "filename": stored_name,
                "original_name": orig_name[:100],
                "role": clean_role,
                "uploaded_at": time.strftime("%Y-%m-%d %H:%M"),
            })
            target["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
            cls._save_raw_unlocked(items)
            return _compute_plugin_view(target, include_script_body=True)

    @classmethod
    def attach_local_sheet(cls, plugin_id: str, src_path: str, role: str = "reference") -> Dict[str, Any]:
        """Ajoute une image locale (ex. vignette tirée d'une vidéo d'exemple) comme planche du style."""
        if not is_valid_plugin_id(plugin_id):
            raise ValueError("Style introuvable.")
        src = Path(src_path)
        if not src.exists() or src.suffix.lower() not in IMAGE_SHEET_EXTS or src.stat().st_size > MAX_SHEET_BYTES:
            raise ValueError("Image invalide.")
        fname = f"cover_{uuid.uuid4().hex[:6]}{src.suffix.lower()}"
        dest_dir = PLUGINS_DIR / plugin_id / "sheets"
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest_dir / fname)
        with _LOCK:
            items = cls._load_raw_unlocked()
            for it in items:
                if it.get("id") == plugin_id:
                    it.setdefault("model_sheets", []).insert(0, {
                        "filename": fname, "original_name": "vidéo d'exemple", "role": role,
                        "uploaded_at": time.strftime("%Y-%m-%d %H:%M"),
                    })
                    it["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
            cls._save_raw_unlocked(items)
        return {"filename": fname}

    @classmethod
    def delete_model_sheet(cls, plugin_id: str, filename: str) -> Dict[str, Any]:
        if not is_valid_plugin_id(plugin_id) or not _SAFE_FILENAME_RE.match(filename or ""):
            raise ValueError("Identifiant invalide.")
        with _LOCK:
            items = cls._load_raw_unlocked()
            target = next((p for p in items if p.get("id") == plugin_id), None)
            if not target:
                raise FileNotFoundError("Plugin introuvable.")
            target["model_sheets"] = [s for s in (target.get("model_sheets") or []) if s.get("filename") != filename]
            target["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
            cls._save_raw_unlocked(items)

        fpath = cls.get_sheet_path(plugin_id, filename)
        if fpath and fpath.exists():
            fpath.unlink(missing_ok=True)
        return cls.get_plugin(plugin_id, include_script_body=True) or {}

    # ---------------------------------------------------------------- vidéo de référence du style
    @classmethod
    def set_reference_video(cls, plugin_id: str, src_path: str = "", file_storage=None, source_url: str = "") -> Dict[str, Any]:
        """Enregistre la vidéo qui montre à quoi ressemble le style (fichier envoyé ou vidéo d'exemple téléchargée)."""
        if not is_valid_plugin_id(plugin_id):
            raise ValueError("Style introuvable.")
        name = (file_storage.filename if file_storage is not None else src_path) or ""
        ext = Path(name).suffix.lower()
        if ext not in REFERENCE_VIDEO_EXTS:
            raise ValueError("Format vidéo non pris en charge (MP4, MOV, M4V ou WEBM).")
        dest_dir = PLUGINS_DIR / plugin_id / "reference"
        dest_dir.mkdir(parents=True, exist_ok=True)
        fname = f"reference_{uuid.uuid4().hex[:6]}{ext}"
        dest = dest_dir / fname
        if file_storage is not None:
            file_storage.save(str(dest))
        else:
            src = Path(src_path)
            if not src.exists():
                raise ValueError("Vidéo introuvable.")
            shutil.copyfile(src, dest)
        if dest.stat().st_size > MAX_REFERENCE_VIDEO_BYTES:
            dest.unlink(missing_ok=True)
            raise ValueError("Vidéo trop lourde (300 Mo max).")
        old = ""
        with _LOCK:
            items = cls._load_raw_unlocked()
            target = next((p for p in items if p.get("id") == plugin_id), None)
            if not target:
                dest.unlink(missing_ok=True)
                raise FileNotFoundError("Plugin introuvable.")
            old = str(target.get("reference_video") or "")
            target["reference_video"] = fname
            if source_url:
                target["reference_url"] = _clean_reference_url(source_url)
            target["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
            cls._save_raw_unlocked(items)
        if old and old != fname and _SAFE_FILENAME_RE.match(old):
            (dest_dir / old).unlink(missing_ok=True)
        return {"filename": fname}

    @classmethod
    def get_reference_video_path(cls, plugin_id: str) -> Optional[Path]:
        if not is_valid_plugin_id(plugin_id):
            return None
        for ext in (".mp4", ".webm", ".mov", ".m4v"):
            bundled = STYLE_REFS_DIR / f"{plugin_id}{ext}"
            if bundled.is_file():
                return bundled
        with _LOCK:
            raw = next((p for p in cls._load_raw_unlocked() if p.get("id") == plugin_id), None)
        fname = str((raw or {}).get("reference_video") or "")
        if not fname or not _SAFE_FILENAME_RE.match(fname):
            return None
        base = (PLUGINS_DIR / plugin_id / "reference").resolve()
        cand = (base / fname).resolve()
        return cand if cand.parent == base and cand.is_file() else None

    @classmethod
    def style_preview(cls, plugin_id: str, renders_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Ce qu'on montre quand on clique sur un style : sa vidéo de référence, sinon un exemple récent fait dans ce style."""
        if not is_valid_plugin_id(plugin_id):
            return {"kind": "none"}
        with _LOCK:
            raw = next((p for p in cls._load_raw_unlocked() if p.get("id") == plugin_id), None)
        if not raw:
            return {"kind": "none"}
        # Seulement une vidéo lue dans Clipoa : jamais de lien vers le site d'origine
        if cls.get_reference_video_path(plugin_id):
            return {"kind": "video", "url": f"/api/plugins/{plugin_id}/reference-video", "label": "Vidéo de référence"}
        rd = Path(renders_dir) if renders_dir else STORAGE_DIR / "renders"
        since = STARTER_LOOK_SINCE.get(plugin_id, 0.0)
        best = None
        try:
            for meta in rd.glob("*/metadata.json"):
                vid = meta.parent / "final_short.mp4"
                if not vid.exists():
                    continue
                mt = vid.stat().st_mtime
                if mt < since or (best and mt <= best[0]):
                    continue
                try:
                    if json.loads(meta.read_text(encoding="utf-8")).get("plugin_id") != plugin_id:
                        continue
                except Exception:
                    continue
                best = (mt, meta.parent.name)
        except Exception:
            best = None
        if best:
            return {"kind": "video", "url": f"/stream/{best[1]}", "label": "Exemple fait avec Clipoa dans ce style"}
        return {"kind": "none"}

    @classmethod
    def get_sheet_path(cls, plugin_id: str, filename: str) -> Optional[Path]:
        if not is_valid_plugin_id(plugin_id) or not _SAFE_FILENAME_RE.match(filename or ""):
            return None
        base = (PLUGINS_DIR / plugin_id / "sheets").resolve()
        candidate = (base / filename).resolve()
        if candidate.parent != base:
            return None
        return candidate if candidate.exists() and candidate.is_file() else None

    @classmethod
    def upload_script_file(cls, plugin_id: str, file_storage, language: Optional[str] = None) -> Dict[str, Any]:
        if not is_valid_plugin_id(plugin_id):
            raise ValueError("ID de plugin invalide.")
        if not file_storage or not file_storage.filename:
            raise ValueError("Aucun fichier script sélectionné.")

        safe = secure_filename(Path(file_storage.filename).name) or "script.py"
        ext = Path(safe).suffix.lower()
        if ext not in ALLOWED_SCRIPT_EXTS:
            raise ValueError(f"Extension de script non autorisée ({ext}). Acceptées : .py, .js, .ts, .sh, .json, .txt, .md.")

        raw_bytes = file_storage.read(MAX_SCRIPT_BYTES + 1)
        if len(raw_bytes) > MAX_SCRIPT_BYTES:
            raise ValueError("Script trop volumineux (max 2 Mo).")
        content = raw_bytes.decode("utf-8", errors="replace")

        ext_to_lang = {".py": "python", ".js": "javascript", ".ts": "javascript", ".sh": "shell", ".json": "json", ".txt": "prompt", ".md": "prompt"}
        detected_lang = language or ext_to_lang.get(ext, "python")

        return cls.update_plugin(
            plugin_id,
            {
                "script_filename": safe,
                "script_language": detected_lang,
                "script_content": content,
            },
        )

    @classmethod
    def build_da_context(cls, plugin_id: Optional[str], preserve_user_script: bool = False) -> str:
        """
        Construit le bloc de contexte Direction Artistique (DA) injecté dans Claude / Gemini
        lorsqu'un créateur sélectionne un Plugin de Style.
        """
        if not plugin_id:
            return ""
        plugin = cls.get_plugin(plugin_id, include_script_body=True)
        if not plugin:
            return ""

        parts: List[str] = [
            f"=== STYLE / DIRECTION ARTISTIQUE (DA) : {plugin['name']} ===",
        ]
        if plugin.get("tagline"):
            parts.append(f"Résumé : {plugin['tagline']}")

        if plugin.get("da_prompt"):
            parts.append(f"Direction Artistique (DA) à respecter strictement :\n{plugin['da_prompt']}")
        else:
            parts.append(
                f"Adapte toute la mise en scène, les décors, les personnages et les scènes dans le style « {plugin['name']} »."
            )

        if not preserve_user_script and plugin.get("narrative_rules"):
            parts.append(f"Règles narratives :\n{plugin['narrative_rules']}")

        # Cette DA vient souvent d'une vidéo de référence précise : ses décors, objets et exemples (ex. « neige,
        # miroirs couverts ») décrivent un STYLE. Sans cette règle, l'IA refait l'histoire de la référence à chaque fois.
        parts.append(
            "RÈGLE D'ORIGINALITÉ : les décors, objets, gimmicks, personnages et exemples cités dans cette DA "
            "décrivent un STYLE (rendu, cadrage, rythme, ton), pas le sujet. L'histoire, son objet-clé, ses lieux et "
            "son retournement viennent UNIQUEMENT de l'idée de l'utilisateur. Ne reprends un élément cité en exemple "
            "que si l'idée le demande explicitement."
        )

        if preserve_user_script:
            parts.append(
                "RÈGLE IMPÉRATIVE : L'utilisateur fournit SON PROPRE SCRIPT parlé. "
                "Conserve son texte parlé mot pour mot dans `full_spoken_script` sans le modifier, "
                "et applique la DA ci-dessus sur le `visual_storyboard`, le `hook_screen_text` et la `social_caption`."
            )

        sheets = plugin.get("model_sheets") or []
        if sheets:
            role_labels = {r["id"]: r["label"] for r in SHEET_ROLES}
            sheet_lines = "\n".join(
                f"- [{role_labels.get(s.get('role', 'reference'), 'Aperçu')}] {s.get('original_name') or s.get('filename')}"
                for s in sheets[:15]
            )
            parts.append(f"Planches de modèles ({len(sheets)}) :\n{sheet_lines}")

        if plugin.get("script_content"):
            snippet = plugin["script_content"].strip()[:1800]
            parts.append(
                f"Script associé ({plugin.get('script_filename') or plugin.get('script_language')}) :\n"
                f"```{plugin.get('script_language', 'python')}\n{snippet}\n```"
            )

        return "\n\n".join(parts)
