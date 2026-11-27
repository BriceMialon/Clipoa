"""
Personnalité de création ClipRoll (Créateur vs Entreprise/Marque) et suivi des 5 comptes concurrents.

- Personnalité « creator » (défaut) : création libre sur n'importe quel sujet.
- Personnalité « business » : optimise tous les scripts pour une entreprise / commerce / marque
  qui n'a pas le temps de filmer (méthode en 3 temps : geste/situation universelle → conseil métier
  ou chiffre concret → présentation naturelle de l'entreprise, de son offre et du CTA à la fin).
  Disponible en édition « perso » ET « public ».
- Suivi de 5 comptes concurrents : repère les shorts qui font >= 2× les vues habituelles du compte
  et prépare un brief d'inspiration structurelle (recette/rythme uniquement, jamais le texte/images/voix).
  Coupé côté serveur en édition « public » via core/edition.py.
"""

from pathlib import Path
import json
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional
from core.edition import is_public
from core.settings_store import load_settings, save_settings

MAX_COMPETITORS = 5
MAX_CUSTOM_PERSONALITIES = 20
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

DEFAULT_PERSONALITY: Dict[str, Any] = {
    "mode": "creator",  # "creator" | "business" | "custom"
    "active_custom_id": "",
    "company_name": "",
    "industry": "",
    "offer": "",
    "audience": "",
    "cta": "",
    "tone": "expert",  # "expert" | "commercial" | "coulisses" | "premium"
}

VALID_TONES = ("expert", "commercial", "coulisses", "premium")

BUSINESS_EXAMPLES: List[Dict[str, str]] = [
    {
        "label": "Opticien",
        "company_name": "Optique Lumière",
        "industry": "Opticien indépendant",
        "offer": "Réglage et nettoyage de lunettes offerts, même achetées ailleurs",
        "audience": "Porteurs de lunettes et habitants du quartier",
        "cta": "Passe nous voir en boutique cette semaine",
        "tone": "expert",
    },
    {
        "label": "Garage auto",
        "company_name": "Garage Saint-Martin",
        "industry": "Garage automobile multimarque",
        "offer": "Diagnostic voyant moteur offert avant tout devis",
        "audience": "Automobilistes locaux",
        "cta": "Prends rendez-vous via le lien en bio",
        "tone": "expert",
    },
    {
        "label": "Boulangerie",
        "company_name": "Maison Levain",
        "industry": "Boulangerie artisanale au levain naturel",
        "offer": "Baguette tradition au levain 24h et coffret découverte du week-end",
        "audience": "Amateurs de bon pain du quartier",
        "cta": "Passe avant 11h pour la fournée chaude",
        "tone": "coulisses",
    },
    {
        "label": "Coiffeur",
        "company_name": "Atelier Nuance",
        "industry": "Salon de coiffure & visagiste",
        "offer": "Diagnostic coupe & soin personnalisé offert au premier rendez-vous",
        "audience": "Clients cherchant une coupe adaptée à leur visage",
        "cta": "Réserve ton créneau en bio",
        "tone": "premium",
    },
]


def get_personality() -> Dict[str, Any]:
    raw = (load_settings().get("personality") or {})
    out = dict(DEFAULT_PERSONALITY)
    if isinstance(raw, dict):
        for k in DEFAULT_PERSONALITY:
            if k in raw and raw[k] is not None:
                out[k] = str(raw[k]).strip()
    if out["mode"] not in ("creator", "business", "custom"):
        out["mode"] = "creator"
    if out["tone"] not in VALID_TONES:
        out["tone"] = "expert"
    if out["mode"] == "custom" and not get_custom_personality(out.get("active_custom_id", "")):
        out["mode"] = "creator"
        out["active_custom_id"] = ""
    return out


def save_personality(payload: Dict[str, Any]) -> Dict[str, Any]:
    cur = get_personality()
    if isinstance(payload, dict):
        mode = str(payload.get("mode", cur["mode"]) or "creator").strip().lower()
        if mode in ("creator", "business", "custom"):
            cur["mode"] = mode
        else:
            cur["mode"] = "creator"
        if "active_custom_id" in payload:
            cur["active_custom_id"] = str(payload.get("active_custom_id") or "").strip()[:64]
        if cur["mode"] == "custom" and not get_custom_personality(cur.get("active_custom_id", "")):
            cur["mode"] = "creator"
            cur["active_custom_id"] = ""
        for field, max_len in (
            ("company_name", 80),
            ("industry", 100),
            ("offer", 220),
            ("audience", 140),
            ("cta", 140),
        ):
            if field in payload:
                cur[field] = str(payload.get(field) or "").strip()[:max_len]
        if "tone" in payload:
            t = str(payload.get("tone") or "expert").strip().lower()
            cur["tone"] = t if t in VALID_TONES else "expert"
    save_settings({"personality": cur})
    return cur


def _normalize_angles(raw_angles: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if isinstance(raw_angles, str):
        for line in raw_angles.splitlines():
            t = line.strip()
            if not t:
                continue
            if ":" in t:
                lbl, topic = t.split(":", 1)
                out.append({"label": lbl.strip()[:48] or "Idée", "topic": topic.strip()[:280]})
            else:
                out.append({"label": t[:40], "topic": t[:280]})
            if len(out) >= 12:
                break
    elif isinstance(raw_angles, list):
        for item in raw_angles[:12]:
            if isinstance(item, dict):
                topic = str(item.get("topic") or "").strip()[:280]
                lbl = str(item.get("label") or topic[:40]).strip()[:48]
                if topic:
                    out.append({"label": lbl or "Idée", "topic": topic})
            elif isinstance(item, str) and item.strip():
                t = item.strip()[:280]
                out.append({"label": t[:40], "topic": t})
    return out


def list_custom_personalities() -> List[Dict[str, Any]]:
    raw = load_settings().get("custom_personalities") or []
    out: List[Dict[str, Any]] = []
    pub = is_public()
    if isinstance(raw, list):
        for item in raw[:MAX_CUSTOM_PERSONALITIES]:
            if not isinstance(item, dict):
                continue
            if pub and item.get("private_owner"):
                continue
            pid = str(item.get("id") or "").strip()[:64]
            name = str(item.get("name") or "").strip()[:60]
            if not pid or not name:
                continue
            out.append({
                "id": pid,
                "name": name,
                "mission": str(item.get("mission") or "").strip()[:350],
                "audience": str(item.get("audience") or "").strip()[:180],
                "tone": str(item.get("tone") or "").strip()[:160],
                "key_points": str(item.get("key_points") or "").strip()[:600],
                "cta": str(item.get("cta") or "").strip()[:200],
                "rules": str(item.get("rules") or "").strip()[:350],
                "angles": _normalize_angles(item.get("angles")),
                "private_owner": bool(item.get("private_owner")),
            })
    return out


def get_custom_personality(pid: str) -> Optional[Dict[str, Any]]:
    pid = str(pid or "").strip()
    if not pid:
        return None
    for p in list_custom_personalities():
        if p["id"] == pid:
            return p
    return None


def save_custom_personality(payload: Dict[str, Any], activate: bool = True) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Données de personnalité invalides.")
    name = str(payload.get("name") or "").strip()[:60]
    if not name:
        raise ValueError("Donne un nom à ta personnalité (ex : Ma Marque, Coach Sport…).")
    raw_list = list(load_settings().get("custom_personalities") or [])
    pid = str(payload.get("id") or "").strip()[:64]
    if not pid:
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:24] or "perso"
        pid = f"{slug}_{uuid.uuid4().hex[:6]}"
    entry: Dict[str, Any] = {
        "id": pid,
        "name": name,
        "mission": str(payload.get("mission") or "").strip()[:350],
        "audience": str(payload.get("audience") or "").strip()[:180],
        "tone": str(payload.get("tone") or "").strip()[:160],
        "key_points": str(payload.get("key_points") or "").strip()[:600],
        "cta": str(payload.get("cta") or "").strip()[:200],
        "rules": str(payload.get("rules") or "").strip()[:350],
        "angles": _normalize_angles(payload.get("angles")),
        "private_owner": bool(payload.get("private_owner")) and not is_public(),
    }
    replaced = False
    for idx, cur in enumerate(raw_list):
        if isinstance(cur, dict) and cur.get("id") == pid:
            raw_list[idx] = entry
            replaced = True
            break
    if not replaced:
        if len(raw_list) >= MAX_CUSTOM_PERSONALITIES:
            raise ValueError(f"Maximum {MAX_CUSTOM_PERSONALITIES} personnalités personnalisées.")
        raw_list.append(entry)
    save_settings({"custom_personalities": raw_list})
    if activate:
        save_personality({"mode": "custom", "active_custom_id": pid})
    return entry


def delete_custom_personality(pid: str) -> bool:
    pid = str(pid or "").strip()
    raw_list = list(load_settings().get("custom_personalities") or [])
    new_list = [x for x in raw_list if not (isinstance(x, dict) and x.get("id") == pid)]
    if len(new_list) == len(raw_list):
        return False
    save_settings({"custom_personalities": new_list})
    cur = get_personality()
    if cur.get("active_custom_id") == pid:
        save_personality({"mode": "creator", "active_custom_id": ""})
    return True


def suggest_active_angles(profile: Dict[str, Any]) -> List[Dict[str, str]]:
    mode = (profile or {}).get("mode")
    if mode == "custom":
        cp = get_custom_personality(profile.get("active_custom_id", ""))
        if cp:
            if cp.get("angles"):
                return cp["angles"]
            nm = cp["name"]
            mission = cp.get("mission") or nm
            return [
                {"label": "Problème → Solution", "topic": f"Pars du problème concret que résout {nm}, montre pourquoi la méthode classique échoue, puis présente {mission}."},
                {"label": "Avant / Après", "topic": f"Montre un avant/après frappant grâce à {nm} ({mission})."},
                {"label": "Idée reçue", "topic": f"Casse une idée reçue dans le domaine de {nm} puis montre concrètement comment {nm} règle ça."},
                {"label": "Démonstration rapide", "topic": f"Démontre en 30 secondes le résultat concret obtenu avec {nm}."},
            ]
    return suggest_business_angles(profile or {})


def suggest_business_angles(profile: Dict[str, Any]) -> List[Dict[str, str]]:
    """Propose 4 angles prêts-à-cliquer adaptés à la fiche entreprise."""
    name = profile.get("company_name") or "mon entreprise"
    ind = profile.get("industry") or "mon métier"
    offer = profile.get("offer") or "notre offre phare"
    return [
        {
            "id": "tip",
            "label": "Conseil métier",
            "topic": f"Un geste du quotidien lié à {ind}, un vrai chiffre ou conseil métier utile, puis présente {name} et {offer} à la fin.",
        },
        {
            "id": "offer",
            "label": "Mettre en avant l'offre",
            "topic": f"Le problème n°1 de nos clients en {ind}, comment éviter l'erreur classique, puis présente {offer} chez {name}.",
        },
        {
            "id": "myth",
            "label": "Idée reçue",
            "topic": f"Une idée reçue très courante sur {ind} démontée en 30 secondes avec un vrai conseil pratique, puis mention naturelle de {name}.",
        },
        {
            "id": "before_after",
            "label": "Avant / Après client",
            "topic": f"Une situation concrète avant/après typique en {ind} qui montre le résultat concret de {offer} chez {name}.",
        },
    ]


def build_personality_prompt_block(profile: Dict[str, Any] = None) -> str:
    """Retourne le bloc d'instructions IA pour la personnalité Entreprise ou Personnalisée active, sinon ''."""
    p = profile if isinstance(profile, dict) else get_personality()
    mode = p.get("mode")
    if mode == "custom":
        cp = get_custom_personality(p.get("active_custom_id", ""))
        if not cp:
            return ""
        lines = [
            f"\n=== PERSONNALITÉ DE CRÉATION : {cp['name']} (OBLIGATOIRE) ===",
            "Respecte strictement cette personnalité, ses messages clés et son appel à l'action dans le script :",
        ]
        if cp.get("mission"):
            lines.append(f"- Objectif / Produit / Promesse : {cp['mission']}")
        if cp.get("audience"):
            lines.append(f"- Public cible : {cp['audience']}")
        if cp.get("tone"):
            lines.append(f"- Ton & rythme : {cp['tone']}")
        if cp.get("key_points"):
            lines.append(f"- Infos clés / Preuves / Dates à intégrer naturellement : {cp['key_points']}")
        if cp.get("cta"):
            lines.append(f"- Appel à l'action final : {cp['cta']}")
        if cp.get("rules"):
            lines.append(f"- Règles & interdits : {cp['rules']}")
        lines.append(
            "STRUCTURE RECOMMANDÉE :\n"
            "01. ACCROCHE (0–2 s) : ouvre par une tension, une question choc ou un contraste fort (jamais une pub molle).\n"
            "02. PREUVE & VALEUR (2–22 s) : illustre concrètement le bénéfice avec un exemple parlant ou un avant/après.\n"
            "03. OFFRE & CTA FINAL (dernières secondes) : glisse naturellement les infos clés (date/offre) et l'appel à l'action.\n"
        )
        return "\n".join(lines)
    if mode != "business":
        return ""
    name = p.get("company_name") or ""
    ind = p.get("industry") or ""
    offer = p.get("offer") or ""
    aud = p.get("audience") or ""
    cta = p.get("cta") or ""
    tone_map = {
        "expert": "expert accessible, pédagogique et rassurant",
        "commercial": "dynamique, clair et orienté conversion",
        "coulisses": "authentique, humain et proche du terrain",
        "premium": "soigné, élégant et haut de gamme",
    }
    tone_desc = tone_map.get(p.get("tone") or "expert", tone_map["expert"])
    lines = [
        "\n=== PERSONNALITÉ ENTREPRISE / MARQUE (OBLIGATOIRE) ===",
        "Ce short est conçu pour promouvoir une entreprise qui n'a pas le temps de filmer.",
    ]
    if name:
        lines.append(f"- Entreprise / Marque : {name}")
    if ind:
        lines.append(f"- Métier / Secteur : {ind}")
    if offer:
        lines.append(f"- Offre / Promesse à mettre en avant : {offer}")
    if aud:
        lines.append(f"- Clientèle cible : {aud}")
    if cta:
        lines.append(f"- Appel à l'action final : {cta}")
    lines.append(f"- Ton souhaité : {tone_desc}")
    lines.append(
        "STRUCTURE ENTREPRISE EN 3 TEMPS (ne fais PAS une pub classique dès la 1re seconde) :\n"
        "01. ACCROCHE (0–4 s) : commence par un geste, une situation ou un problème concret que tout le monde reconnaît.\n"
        "02. VALEUR MÉTIER (4–22 s) : donne un vrai conseil de professionnel, un chiffre réel ou une explication utile qui prouve l'expertise.\n"
        "03. ENTREPRISE & OFFRE À LA FIN (dernières secondes) : cite naturellement l'entreprise, son offre phare et l'appel à l'action sans paraître agressif.\n"
    )
    return "\n".join(lines)


# ---------- 5 Comptes Concurrents (Outliers >= 2x) ----------

def list_competitors() -> List[Dict[str, str]]:
    raw = load_settings().get("competitors") or []
    out: List[Dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw[:MAX_COMPETITORS]:
            if isinstance(item, str):
                h = item.strip()[:200]
                if h:
                    out.append({"handle": h, "label": h})
            elif isinstance(item, dict):
                h = str(item.get("handle") or item.get("url") or "").strip()[:200]
                if h:
                    lbl = str(item.get("label") or h).strip()[:80]
                    out.append({"handle": h, "label": lbl})
    return out


def save_competitors(items: List[Any]) -> List[Dict[str, str]]:
    clean: List[Dict[str, str]] = []
    seen = set()
    for item in (items or []):
        if len(clean) >= MAX_COMPETITORS:
            break
        if isinstance(item, str):
            h = item.strip()[:200]
            lbl = h
        elif isinstance(item, dict):
            h = str(item.get("handle") or item.get("url") or "").strip()[:200]
            lbl = str(item.get("label") or h).strip()[:80]
        else:
            continue
        if not h or h.startswith("-"):
            continue
        key = h.lower()
        if key in seen:
            continue
        seen.add(key)
        clean.append({"handle": h, "label": lbl or h})
    save_settings({"competitors": clean})
    return clean


def build_recipe_inspiration_brief(outlier: Dict[str, Any], profile: Dict[str, Any] = None) -> str:
    """
    Construit un brief d'inspiration structurelle (recette/rythme/hook uniquement)
    sans jamais copier l'histoire, le texte, les images ou la voix du concurrent.
    """
    title = str(outlier.get("title") or "Short viral").strip()[:120]
    ratio = outlier.get("ratio") or 2.0
    dur = int(outlier.get("duration") or 0)
    account = str(outlier.get("competitor") or "").strip()
    p = profile if isinstance(profile, dict) else get_personality()

    target_ctx = ""
    if p.get("mode") == "custom":
        cp = get_custom_personality(p.get("active_custom_id", ""))
        if cp:
            target_ctx = f" Adapte cette recette à ma personnalité « {cp['name']} » ({cp.get('mission') or ''})."
    elif p.get("mode") == "business" and (p.get("company_name") or p.get("industry")):
        target_ctx = (
            f" Adapte cette recette à mon entreprise {p.get('company_name') or ''} "
            f"({p.get('industry') or ''}) avec mon offre : {p.get('offer') or 'notre service'}."
        )
    else:
        target_ctx = " Invente un sujet et une histoire 100 % neufs dans ma niche."

    return (
        f"S'inspirer de la RECETTE structurelle du short « {title} »"
        + (f" ({account}, {ratio}× les vues habituelles" if account else f" ({ratio}× les vues habituelles")
        + (f", ~{dur}s)" if dur else ")")
        + " : reprends uniquement la mécanique d'accroche, le rythme des plans et la construction de tension. "
        "INTERDICTION ABSOLUE de copier l'histoire, le texte, les images ou la voix d'origine."
        + target_ctx
    )


def scan_competitors(threshold: float = 2.0, limit: int = 20) -> Dict[str, Any]:
    """Scanne les 5 comptes concurrents et renvoie tous les shorts >= threshold × vues habituelles."""
    from core.scraper import CompetitorScraper
    from core.security import validate_public_http_url

    comps = list_competitors()
    if not comps:
        raise ValueError("Ajoute d'abord entre 1 et 5 comptes concurrents à suivre.")

    profile = get_personality()
    all_outliers: List[Dict[str, Any]] = []
    account_summaries: List[Dict[str, Any]] = []
    errors: List[str] = []

    for c in comps:
        raw_h = c["handle"]
        target_url = raw_h
        if not raw_h.startswith("@"):
            try:
                target_url = validate_public_http_url(raw_h)
            except ValueError as ve:
                errors.append(f"{raw_h} : {ve}")
                continue
        try:
            res = CompetitorScraper.find_outliers(target_url, limit=limit, threshold=threshold)
            avg_v = res.get("average_views") or 0
            outs = res.get("outliers") or []
            account_summaries.append({
                "handle": raw_h,
                "scanned": res.get("total_scanned", 0),
                "average_views": avg_v,
                "outliers_count": len(outs),
            })
            for o in outs:
                item = dict(o)
                item["competitor"] = raw_h
                item["account_avg_views"] = avg_v
                item["recipe_brief"] = build_recipe_inspiration_brief(item, profile=profile)
                all_outliers.append(item)
        except Exception as e:
            errors.append(f"{raw_h} : {e}")

    all_outliers.sort(key=lambda x: (float(x.get("ratio") or 0), int(x.get("views") or 0)), reverse=True)
    return {
        "competitors": comps,
        "accounts": account_summaries,
        "outliers": all_outliers[:40],
        "errors": errors,
        "threshold": threshold,
    }
