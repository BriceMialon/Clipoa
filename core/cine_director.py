"""
Réalisateur « Roblox 3D Ciné » (qualité Docteur Shark / série d'horreur) pour n'importe quelle histoire.

1. La narration (mots Whisper) devient timeline.json au format du moteur.
2. L'IA choisie (Claude ou Antigravity) écrit les plans en code (shots.js) avec l'API du moteur : décors, acteurs,
   expressions, caméras, éclairages, effets.
3. Clipoa ouvre la scène, prend une image par plan et détecte les défauts (erreur JS, caméra dans un objet, tête coupée,
   personnages qui se traversent, image noire). L'IA corrige (2 tours max).
4. Rendu final 1080x1920 à 30 i/s, un MP4 sans son que Clipoa habille ensuite (voix, musique, sous-titres).
C'est plus long et plus coûteux en tokens que les styles Blender : l'interface le signale avant de lancer.
"""
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.cine_setup import ENGINE_DIR, EPISODES_DIR, is_ready

END_RE = re.compile(r"[.!?…]$")
CUT_RE = re.compile(r"[,;:]$")

API_DOC = r"""
# API du moteur three.js (fichier `shots.js` à écrire)

```js
export function buildShots(ctx) {
  const { world: w, timeline: T, W, S: SH, THREE } = ctx;
  const line = (id) => T.lines.find((l) => l.id === id);          // line('L3').start
  const chunk = (id, k) => line(id).chunks[k].start;              // début du k-ième morceau (coupé aux virgules)
  // objets / personnages de CETTE histoire : créés une fois, cachés et remis en place au début de chaque plan
  const hero = ctx.own(W.makeVillager({ name: 'hero', skin: '#f0c9a0', shirt: '#2e86de', pants: '#2c3e50', hair: '#3b2a20', hairStyle: 'spiky' }));
  const S = [ { name: 'p01_...', start: 0, preset: 'day', setup: (c) => {...}, update: (c, t, p) => {...} }, ... ];
  S.forEach((s, i) => (s.end = i + 1 < S.length ? S[i + 1].start : T.duration));   // OBLIGATOIRE, à garder tel quel
  return S;
}
```
- Plan : `{name, start, preset, post?, flash?, setup(c), update(c, t, p)}`. `t` = secondes depuis le début du plan, `p` = 0→1.
  Le monde est remis à zéro avant chaque plan (acteurs cachés, objets à leur place) : tout montrer dans `setup`.
- Éclairages `preset` : `day`, `overcast`, `golden`, `night`, `fog`, `frisson` (brume froide + contre-jour, moment glaçant).
  `post: 'sepia'` ou `post: 'bw'` = flashback ; `flash: true` = flash blanc de révélation.
- Caméra : `c.camera({pos:[x,y,z], target:[x,y,z], fov:40}, {pos, target, fov}, 'inOut')` (travelling du 1er au 2e cadrage).
  `c.shadowFocus(x, z, taille)` centre les ombres sur l'action (toujours l'appeler). `c.shake(0.05)` tremblement.
  `c.wordTime('mot')` = instant (s, dans le plan) où le mot est dit, ou null. `c.talk(acteur)` = il bouge la bouche sur la voix.
- Acteurs : `W.makeVillager({name, skin, shirt, pants, shoes, hair, hairStyle:'flat'|'puffy'|'spiky'|'long'|'bald',
  suit, tie, chain, apron, coat, shawl, beard, mustache, glasses, hood})` → toujours via `ctx.own(...)`.
  Hauteur ≈ 5,4 ; visage vers y ≈ 4,6. Ils regardent vers +z quand rotY = 0.
  `w.place(a, x, z, rotY)` (le rend visible), `w.walk(a, [x0,z0], [x1,z1], t0, t1, t, {speed, face})` dans update,
  `w.pose(a, {armL:{x,z}, armR:{x,z}, head:{x,y,z}, torso:{x}, legL:{x}, legR:{x}})`,
  `a.userData.setExpr('neutral'|'smile'|'laugh'|'worried'|'shocked'|'angry'|'shout')`. Clignement et respiration automatiques.
- Décor existant (village centré sur l'origine, regard vers -z) : sol pavé, mairie z=-30, fontaine en (0,0) rayon 3,4,
  étals de marché `w.stalls`, maisons `w.houses.L1..L4` (x=-24) et `R1, R2, R4` (x=24) avec `userData.door.rotation.y`,
  montagne z=-230, château (85,-150), portail z=38, lampadaires. Intérieurs déjà construits loin du village (à montrer avec
  `.visible = true`) : `w.bedroom` (chambre, -150,0,0), `w.alley` (ruelle de nuit, -150,0,320), `w.stairwell` (cage d'escalier,
  -150,0,240), `w.shop` (boutique, 0,0,-30, cacher alors la mairie `w.townhall.visible=false`), `w.bank`, `w.mill` (112,0,24), `w.field` (100,0,42).
  Accessoires : `w.goldCar` (voiture), `w.priceBoard`, `w.ticker` (écran de courbe `w.ticker.userData.drawChart(p)`), `w.coins`
  (`w.coinRain(x,z,t0)`), neige `w.snowOn(x,z)`, pluie `w.rainOn(x,z)`. La bannière du marché est cachée par défaut (`w.banner`).
- Nouveaux objets avec les briques du moteur : `SH.rbox(largeur, hauteur, profondeur, '#couleur', arrondi)` (bloc arrondi, renvoie
  un Mesh), `new THREE.Group()`, `W.makeHouse({wall, roof, floors})`, `W.makeTree()`, `W.makeLamp(true)`, `W.textTex(...)`,
  `W.canvasTex(w, h, (ctx2d, w, h) => {...})` + `W.plane(l, h, tex)` pour un panneau ou un écran. Toujours `ctx.own(groupe)`.

# Règles de mise en scène (style Docteur Shark : vidéo 3D en blocs, qualité ciné)
- 1 plan par phrase ou morceau de phrase, 1,5 à 4 s chacun (≈ 1 plan toutes les 2,5 s). `start` strictement croissant,
  premier plan à 0, calés sur `line()` / `chunk()`. Varier : plan d'ensemble aérien, plan taille, gros plan visage, plongée,
  contre-plongée, plan d'objet. Jamais deux cadrages identiques de suite.
- Caméra 9:16, fov 40 : largeur visible ≈ 0,41 × distance. Corps entier ≥ 12 unités de distance, plan taille 8-10, visage 5-6.
  Gros plan : viser le menton à 60 % de la hauteur, garder le haut de la tête dans le cadre. Travelling lent (3-8 %).
- Jamais la caméra dans un objet (fontaine rayon 3,4, maisons x=±24). Deux personnages à plus de 2,5 unités l'un de l'autre.
  La nuit, pas de lampadaire allumé à moins de 3 unités d'un visage.
- L'émotion se voit sur les visages (setExpr) à chaque plan ; le moment fort a son éclairage (`frisson`, `night`) et son effet.
- Les objets dont parle la phrase sont MONTRÉS (panneau, écran, objet construit) : c'est ce qui rend la vidéo vivante.
- Ne montre jamais Docteur Shark ni ses requins (w.shark, w.petitShark, w.mamanShark) sauf si l'histoire le demande.
"""


def build_timeline(words: List[Dict[str, Any]], duration: float) -> Dict[str, Any]:
    """Mots Whisper → lignes (phrases) et morceaux (coupés aux virgules), au format du moteur."""
    lines: List[Dict[str, Any]] = []
    cur: List[Dict[str, Any]] = []

    def flush():
        if not cur:
            return
        chunks, ch = [], []
        for w in cur:
            ch.append(w)
            if CUT_RE.search(w["w"]):
                chunks.append(ch)
                ch = []
        if ch:
            chunks.append(ch)
        lines.append({
            "id": f"L{len(lines) + 1}", "text": " ".join(w["w"] for w in cur), "start": cur[0]["start"],
            "chunks": [{"text": " ".join(w["w"] for w in c), "start": c[0]["start"], "end": c[-1]["end"]} for c in chunks],
            "words": list(cur),
        })
        cur.clear()

    for w in words or []:
        txt = str(w.get("word") or w.get("w") or "").strip()
        if not txt:
            continue
        cur.append({"w": txt, "start": round(float(w.get("start", 0.0)), 3), "end": round(float(w.get("end", w.get("start", 0.0))), 3)})
        if END_RE.search(txt) or len(cur) >= 22:
            flush()
    flush()
    if lines:
        lines[0]["start"] = 0.0
        lines[0]["chunks"][0]["start"] = 0.0
    for i, L in enumerate(lines):
        L["end"] = lines[i + 1]["start"] if i + 1 < len(lines) else round(duration, 3)
    return {"duration": round(duration, 3), "lines": lines}


def has_blocking_errors(report: Optional[Dict[str, Any]]) -> bool:
    """Vrai si la scène ne démarre pas ou si un plan plante (les petits défauts de cadrage ne bloquent pas le rendu)."""
    if not report or "problems" not in report:
        return True
    return any("ne démarre pas" in p or "erreur JavaScript" in p for p in report["problems"])


def build_prompt(script: Dict[str, Any], timeline: Dict[str, Any], da_hint: str, example: str) -> str:
    tl = "\n".join(
        f"{L['id']} {L['start']:.2f}-{L['end']:.2f}s : « {L['text']} »"
        + ("" if len(L["chunks"]) < 2 else "  [morceaux : " + " | ".join(f"{k}@{c['start']:.2f}s « {c['text']} »" for k, c in enumerate(L["chunks"])) + "]")
        for L in timeline["lines"]
    )
    return f"""Tu es réalisateur 3D. Tu mets en scène un Short vertical en 3D blocky (style Roblox, qualité ciné) avec le moteur three.js
décrit ci-dessous. Écris le fichier `shots.js` COMPLET pour CETTE histoire : invente les décors et les personnages qui
correspondent au script (pas le village de Docteur Shark tel quel si l'histoire se passe ailleurs : construis ou réaménage).

Titre : {script.get('title', '')}
{('Direction artistique (extrait) : ' + da_hint[:1500]) if da_hint else ''}

Narration calée (durée totale {timeline['duration']:.2f} s) :
{tl}

{API_DOC}

# Exemple réel (épisode 1 de Docteur Shark, extrait) — même API, autre histoire :
```js
{example[:9000]}
```

Réponds UNIQUEMENT avec le code JavaScript complet de shots.js dans un bloc ```js ... ```."""


def _extract_js(raw: str) -> str:
    m = re.search(r"```(?:js|javascript)?\s*\n([\s\S]*?)```", raw or "")
    code = (m.group(1) if m else raw or "").strip()
    if "export function buildShots" not in code:
        raise ValueError("le code reçu ne contient pas buildShots")
    return code


def _ask(prompt: str, engine: str, model: Optional[str]) -> str:
    if engine == "antigravity":
        from core.antigravity_bridge import AntigravityBridge
        return AntigravityBridge.query(prompt, model=model, timeout=600)
    from core.claude_bridge import ClaudeBridge
    return ClaudeBridge.query(prompt, action="cine_shots")


def direct(session_id: str, script: Dict[str, Any], words: List[Dict[str, Any]], duration: float, out_mp4: str,
           engine: str = "claude", model: Optional[str] = None, da_hint: str = "",
           progress: Optional[Callable[[int, str], None]] = None, max_fixes: int = 2,
           size=(1080, 1920), fps: int = 30) -> str:
    """Écrit, vérifie et rend la vidéo Ciné. Lève une exception si le moteur n'est pas installé ou si tout échoue."""
    from core import cine_render

    def _p(pct, msg):
        if progress:
            progress(pct, msg)

    if not is_ready():
        raise RuntimeError("Moteur Ciné non installé (Fabrique → Installer le moteur Ciné)")
    ep = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:60]
    ep_dir = EPISODES_DIR / ep
    (ep_dir / "audio").mkdir(parents=True, exist_ok=True)
    timeline = build_timeline(words, duration)
    (ep_dir / "audio" / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=1), encoding="utf-8")
    example = (ENGINE_DIR / "exemple_plans.js").read_text(encoding="utf-8") if (ENGINE_DIR / "exemple_plans.js").exists() else ""
    eng_lbl = "Antigravity" if engine == "antigravity" else "Claude"

    shots_js = ep_dir / "shots.js"
    if not shots_js.exists():
        _p(56, f"🎬 [3/4] {eng_lbl} écrit les plans 3D de ton histoire (mode Ciné, ~2-4 min)…")
        shots_js.write_text(_extract_js(_ask(build_prompt(script, timeline, da_hint, example), engine, model)), encoding="utf-8")

    report: Dict[str, Any] = {}
    for attempt in range(max_fixes + 1):
        _p(60, f"🔍 [3/4] Planche de contrôle des plans (essai {attempt + 1})…")
        try:
            report = cine_render.preview(ep, str(ep_dir / "preview"))
            problems = report["problems"]
        except Exception as e:
            problems = [f"la scène ne démarre pas : {e}"]
        (ep_dir / "defauts.txt").write_text("\n".join(problems) + "\n", encoding="utf-8")
        if not problems or attempt == max_fixes:
            break
        _p(61, f"🛠️ [3/4] {eng_lbl} corrige {len(problems)} défaut(s) de plans…")
        fix = (f"Voici ton fichier shots.js :\n```js\n{shots_js.read_text(encoding='utf-8')}\n```\n\n"
               f"La planche de contrôle signale ces défauts :\n- " + "\n- ".join(problems[:20]) +
               f"\n\nRappel de l'API :\n{API_DOC}\n\nCorrige-les. Réponds UNIQUEMENT avec le shots.js complet corrigé dans ```js ... ```.")
        try:
            new_code = _extract_js(_ask(fix, engine, model))
            shutil.copy(shots_js, ep_dir / f"shots_v{attempt + 1}.js")
            shots_js.write_text(new_code, encoding="utf-8")
        except Exception as e:
            print(f"⚠️ Correction des plans impossible ({e}) : on garde la version actuelle.")
            break
    if has_blocking_errors(report):
        raise RuntimeError("Les plans 3D contiennent encore des erreurs ; repli sur le rendu Blender.")

    t0 = time.time()

    def _prog(done, total):
        el = time.time() - t0
        eta = int(el / max(1, done) * (total - done) / 60)
        _p(62 + int(12 * done / max(1, total)), f"🎥 [3/4] Rendu Ciné image {done}/{total} · encore ≈ {eta} min")

    return cine_render.film(ep, out_mp4, w=size[0], h=size[1], fps=fps, progress=_prog)
