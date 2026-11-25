# ShortCrew Local (Open Replica) 🎬🚀

Réplique autonome, locale et sans abonnement récurrent de **ShortCrew** (`shortcrew.fr`), conçue pour ton utilisation personnelle avec **Claude**.

---

## 🌟 Ce que fait le projet

1. **Détection des Pépites Virales (`Le Cloneur`)** :
   - Scanne un compte concurrent (YouTube Shorts ou TikTok).
   - Calcule la moyenne des vues du compte et isole les vidéos qui font au moins **$\ge 2\times$ l'audience habituelle**.
2. **Rétro-Ingénierie de la Recette** :
   - Télécharge et transcrit le short concurrent en local via **Whisper**.
   - Déconstruit la mécanique virale (accroche des 2 premières secondes, rythme narratif, éléments d'écran, boucle de fin).
   - Ne conserve rien de l'ancienne vidéo (ni voix, ni images, ni texte) pour garantir du contenu 100% original.
3. **Scénarisation & Adaptation (`Le Scénariste`)** :
   - Écrit un script percutant adapté à ta thématique et à ton style oral (130-150 mots pour 45-60s).
4. **Production Vidéo Automatique (`Le Réalisateur`)** :
   - Synthétise une **voix française ultra-naturelle et 100% gratuite** (via *edge-tts* ou ElevenLabs en option).
   - Calcule les sous-titres dynamiques mot-par-mot synchronisés.
   - Assemble une vidéo verticale 1080x1920 (9:16) avec accroche visuelle, arrière-plan et sous-titres animés.
   - Compatible avec **Blender** pour générer des animations 3D sans frais.
5. **Contrôle Qualité Automatique (`Le Contrôle`)** :
   - Audite la vidéo et le script, attribue une note sur 10 et valide avant publication.
6. **Retouche Ciblée en Langage Naturel** :
   - Tu peux demander : *"refais le début pour qu'il soit plus percutant"*, et l'agent modifie uniquement le segment ciblé sans toucher au reste.

---

## 📁 Architecture du projet

```
shortcrew_clone/
├── cli.py                     # Interface en ligne de commande (CLI)
├── app.py                     # Serveur Web & Dashboard interactif (port 8080)
├── config.py                  # Chemins, clés d'API et configurations
├── core/
│   ├── scraper.py             # Scraping TikTok / Shorts & détection des outliers
│   ├── transcriber.py         # Transcription locale faster-whisper
│   ├── voice_engine.py        # Voix française naturelle gratuite (ou ElevenLabs)
│   ├── video_composer.py      # Moteur de rendu vidéo 1080x1920 & sous-titres ASS
│   ├── blender_engine.py      # Moteur 3D headless Blender CLI
│   ├── quality_controller.py  # Audit et scoring qualité
│   ├── postiz_client.py       # Publication automatique TikTok, Shorts, Reels
│   ├── claude_bridge.py       # Pont Claude (Claude Code Pro/Max ou API)
│   └── pipeline.py            # Orchestrateur central
├── agents/
│   ├── prompts.py             # Définitions des rôles et prompts système
│   └── team.py                # Agents (Cloneur, Scénariste, Stratège, Contrôle)
├── templates/
│   └── index.html             # Interface web sombre épurée inspirée de ShortCrew
└── storage/                   # Dossier contenant tes vidéos, audios et sous-titres
```

---

## 🚀 Guide de Démarrage Rapide

### 1. Activer ton compte Claude
Le projet est conçu pour utiliser ton abonnement **Claude Pro ou Max** via Claude Code déjà installé sur ta machine :
```bash
claude
```
*(Connecte-toi simplement avec ton compte Claude habituel. 0 centime d'API supplémentaire).*

*(Alternative : Si tu préfères l'API Anthropic classique, exporte simplement ta clé : `export ANTHROPIC_API_KEY="sk-ant-..."`)*.

---

### 2. Lancer le Dashboard Visuel (Web UI)
Pour piloter l'application depuis ton navigateur :
```bash
./venv/bin/python cli.py ui
```
Puis ouvre : **http://localhost:8080**

Tu y trouveras :
- **Accueil** : Tableau de bord de ta semaine et lecteur vidéo.
- **La Fabrique** : Tape une idée et obtiens ta vidéo terminée en 1 clic.
- **Concurrents** : Colle le lien d'une chaîne pour voir les pépites et cloner leur recette.
- **L'Équipe IA** : Aperçu des 7 agents.

---

### 3. Utilisation en Ligne de Commande (CLI)

#### A. Scanner un concurrent pour détecter ses meilleures vidéos ($\ge 2\times$ la moyenne) :
```bash
./venv/bin/python cli.py scan https://www.youtube.com/@nom_de_chaine/shorts
```

#### B. Cloner la recette d'une vidéo virale pour ton propre sujet :
```bash
./venv/bin/python cli.py clone "https://www.youtube.com/shorts/XXXX" --topic "Pourquoi ton futur client demande à ChatGPT et pas à toi"
```

#### C. Fabriquer un short directement :
```bash
./venv/bin/python cli.py make --topic "3 astuces méconnues pour doubler son salaire en dev"
```

#### D. Retoucher un short avec tes mots :
```bash
./venv/bin/python cli.py revise <session_id> --feedback "Refais le hook du début pour qu'il soit plus mystérieux"
```

#### E. Générer la stratégie des 5 shorts de la semaine :
```bash
./venv/bin/python cli.py week --niche "Intelligence Artificielle"
```

---

## ⚙️ Options & Écosystème

* **Voix off** : Par défaut, l'application utilise la voix naturelle française `fr-FR-VivienneMultilingualNeural` (100% gratuite). Tu peux aussi renseigner ta clé `ELEVENLABS_API_KEY` dans `config.py` si tu souhaites utiliser ta propre voix clonée.
* **3D Blender** : Pour activer les scènes 3D gratuites, installe [Blender](https://www.blender.org) dans `/Applications`. L'application le pilotera automatiquement en arrière-plan sans ouvrir l'interface.
* **Publication automatique (Postiz)** : Démarre Postiz en Docker ou sur le cloud et renseigne `POSTIZ_API_KEY` dans `config.py` pour publier automatiquement sur TikTok, YouTube et Instagram aux heures programmées.
