# SYNC_CLAUDE.md — Journal natif Antigravity → Claude (auto-mis à jour)

> **Remplacé le 27/11/2026 par `docs/HANDOFF.md`** (journal unique Claude ↔ Antigravity, règles dans `AGENTS.md`). Conservé pour l'historique.

> **Usage** : Ce fichier est mis à jour automatiquement par Antigravity après chaque bloc de modifications, pour que Claude puisse lire directement l'état exact du repo sans relais manuel de Brice.

- **Dernière mise à jour** : 2026-11-26 14:46 CET
- **Base Git** : `main` (`6446034`) — **rien n'a été commité ni poussé**.
- **Tests vérifiés** : `python3 -m unittest discover -s tests -q` → **`Ran 187 tests — OK (skipped=8)`** + `py_compile` OK sur tous les fichiers modifiés/créés.
- **Identifiants déployés (GARANTIS INTACTS)** : `clipoa-oauth`, `clipoa-license`, callbacks OAuth, `~/Library/Clipoa`, `%LOCALAPPDATA%\Clipoa` n'ont **pas** été touchés.
- **Règle de travail convenue** : à partir du prochain chantier parallèle, Antigravity travaillera dans un worktree dédié (`git worktree add ../cliproll-gemini -b gemini/<sujet>`) puis PR.

---

## Résumé des modifications présentes dans le dossier de travail

### 1. Nouveaux fichiers
| Fichier | Rôle |
|---|---|
| `core/agent_team.py` | Orchestrateur **Équipe d'agents IA** (`Orchestrateur · Stratège Rétention · Scénariste · Producteur · Vérificateur`) pour la barre du haut. Exécute les missions (semaine 5 vidéos, audit 12 Shorts, refaire pire vidéo, 5 hooks 1.5s, création 1 vidéo) et bloque toute publication/suppression auto (`blocked_safety`). |
| `core/retention_audit.py` | Les **8 prompts `@jeffar_ai`** : `audit_channel()`, `generate_hooks_1_5s()`, `optimize_script_retention()`, `swipe_away_audit()`, avec parseur JSON robuste (`_extract_json_value`). |
| `mcp_server/cliproll_mcp.py` & `mcp_server/README.md` | Serveur MCP stdio JSON-RPC 2.0 (stdlib Python, 0 dépendance) exposant 7 outils ClipRoll à Claude Desktop / Claude Code. |
| `static/logos/{facebook,facebook-white,elevenlabs,elevenlabs-white}.svg` | 4 logos SVG officiels manquants. |
| `docs/antigravity-handoff/veille-x-et-seo/` | Veille X triée Phase 1 (dès maintenant) vs Phase 2 (post-lancement SEO/GEO `cliproll.app`). |
| `docs/antigravity-handoff/STRATEGIE_AFFILIATION_CLIPROLL.md` | Comparatif & recommandation affiliation (Temps gratuit BYOK dès V1 + 25 % récurrent créateurs ensuite). |

### 2. Fichiers modifiés
| Fichier | Ce qui a changé |
|---|---|
| `app.py` | +6 routes : `POST /api/channel-stats/tiktok-handle`, `POST /api/channel-stats/audit`, `POST /api/script/optimize-retention`, `POST /api/script/swipe-audit`, `GET /api/agent-team/roster`, `POST /api/agent-team/run`. |
| `core/channel_stats.py` | Cache isolé par compte actif (`workspace.current()`), support TikTok API v2 + fallback `yt-dlp` avec `@handle` sauvegardé par workspace (`set_tiktok_handle`), `remake_request()` enrichi des règles `@jeffar_ai`. |
| `core/video_composer.py` & `core/video_editor.py` | Encodage H.264 accéléré sans perte de qualité (`-preset fast -threads 0`, `-crf 19`/`20` conservé). |
| `templates/index.html` & `static/css/cliproll.css` | Toggle **Équipe IA / Aide** dans la barre du haut, indicateur live **`X vidéos en fabrication`** dans la topbar, nouvelle vue **`Fabrique`** (cartes 9:16 + redirection auto au lancement), onglet **`Montage`** à 2 options strictes (*Vidéo courte* + *Longue vidéo en shorts*), bouton **« Cloner la vidéo »** dans **S'inspirer**, **« Audit rétention (12 Shorts) »** + champ `@handle` TikTok dans **Statistiques**, **« Optimiser rétention » / « Audit anti-swipe »** dans **Créer**, suppression des emojis décoratifs IA (remplacés par SVG DA ClipRoll), fix carré rouge emoji dans `#home-hello-name` (`.cr-emoji-native`). |

### 3. Renommages demandés par Brice (`clipoa*` → `cliproll*`)
- `static/css/clipoa-ui.css` → `static/css/cliproll-ui.css`
- `static/js/clipoa_{elevenlabs,onboarding,support,update,ux}.js` → `static/js/cliproll_*.js`
- `tests/test_clipoa.py` → `tests/test_cliproll.py`
- `packaging/windows/clipoa_stub.py` → `packaging/windows/cliproll_stub.py` (+ `packaging/windows/build_msix.ps1`)
- `Clipoa.command` → `ClipRoll.command`
- Références mises à jour dans `templates/index.html`, `static/css/cliproll.css`, `tests/test_{crash_report,onboarding,style_plugins}.py`, `CLAUDE.md`.
