"""
Choix automatique du style d'après l'idée (aucun appel à l'IA : instantané et gratuit).

Utilisé quand l'utilisateur n'a pas choisi de style lui-même. Les mots-clés visent les styles
livrés ; un style perso est retenu si les mots de son nom apparaissent dans l'idée.
Jamais de style « lourd » (mode Ciné) : trop long pour un choix automatique.
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional

DEFAULT_STYLE = "2d_monde_3d"  # Stickman : convient à la plupart des histoires

KEYWORDS = {
    "roblox_3d": ("roblox", "minecraft", "jeu video", "jeux video", "gamer", "gaming", "noob", "obby",
                  "brainrot", "skibidi", "bloc", "cube", "pixel", "fortnite", "avatar", "serveur"),
    "fete_en_folie": ("fete", "anniversaire", "soiree", "noel", "mariage", "vacances", "apero", "danse",
                      "carnaval", "halloween", "nouvel an", "party", "festival", "plage", "ete"),
    "explainer_2d": ("pourquoi", "comment", "astuce", "conseil", "chiffre", "fait", "science", "argent",
                     "economie", "explique", "top", "lecon", "tuto", "sante", "budget", "invest",
                     "salaire", "%", "statistique", "etude", "cerveau", "corps humain", "methode"),
    "parabole_3_destins": ("destin", "trois", "3 personnes", "3 types", "3 facons", "choix", "fable", "parabole",
                           "imagine", "difference entre", "s'enrichissent", "riches", "habitude"),
    "2d_monde_3d": ("quand", "pov", "histoire", "il etait", "couple", "ecole", "travail", "riche",
                    "pauvre", "maison", "ville", "famille", "ami", "patron", "voisin", "moi"),
}

LABELS = {
    "roblox_3d": "ça parle de jeu vidéo",
    "fete_en_folie": "c'est festif",
    "explainer_2d": "ça explique quelque chose",
    "parabole_3_destins": "ça compare des choix",
    "2d_monde_3d": "c'est une histoire",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return " " + "".join(c for c in s if not unicodedata.combining(c)) + " "


def _hit(word: str, text: str) -> bool:
    w = _norm(word).strip()
    if not w:
        return False
    return w in text if not w[0].isalnum() else (" " + w) in text  # début de mot : « invest » trouve « investir »


def suggest_style(topic: str, plugins: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Renvoie {"plugin_id", "name", "reason"} ou None s'il n'y a aucun style utilisable."""
    usable = [p for p in plugins or [] if p.get("id") and not p.get("heavy") and not p.get("hidden")]
    if not usable:
        return None
    ids = {p["id"]: p for p in usable}
    text = _norm(topic)
    scores: Dict[str, int] = {}

    for pid, words in KEYWORDS.items():
        if pid in ids:
            scores[pid] = sum(1 for w in words if _hit(w, text))
    # styles perso : les mots de leur nom (≥ 5 lettres) présents dans l'idée
    for pid, p in ids.items():
        if pid in KEYWORDS:
            continue
        words = [w for w in re.findall(r"[a-z]+", _norm(p.get("name", ""))) if len(w) >= 5]
        hit = sum(1 for w in words if w in text)
        if hit:
            scores[pid] = hit * 2

    best = max(scores.items(), key=lambda kv: kv[1], default=(None, 0))
    if best[1] > 0:
        pid = best[0]
        reason = LABELS.get(pid, "ton idée ressemble à ce style")
    else:
        pid = DEFAULT_STYLE if DEFAULT_STYLE in ids else usable[0]["id"]
        reason = "c'est le plus polyvalent"
    return {"plugin_id": pid, "name": ids[pid].get("name", pid), "reason": reason}
