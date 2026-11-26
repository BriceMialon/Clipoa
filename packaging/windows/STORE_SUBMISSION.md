# Soumission Microsoft Store (MSIX) — Guide ClipRoll Windows

## 1. Prérequis Partner Center
- Compte **Microsoft Partner Center** (individuel, gratuit).
- Réserver le nom de l'application (`ClipRoll`) dans Partner Center → récupérer les valeurs exactes de :
  - `Identity Name` (ex. `BriceMialon.Clipoa`)
  - `Publisher` (ex. `CN=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX`)
  - `PublisherDisplayName`
- Passer ces valeurs au workflow GitHub Actions **Build Windows (MSIX & Web)** (déclenchement manuel `workflow_dispatch`).
- **Uploader le fichier `.msix` NON signé** : le Microsoft Store le signe gratuitement lors de la publication.

## 2. Justification `runFullTrust` (à copier dans Partner Center → Submission options)
> ClipRoll is a local desktop video-creation application packaged as MSIX. It requires `runFullTrust` to run a local HTTP server (`127.0.0.1`), manage the Windows system tray icon, store user media projects in `%LOCALAPPDATA%\Clipoa`, and invoke local media rendering tools (Blender and FFmpeg) as subprocesses.

## 3. Transparence fiche Store (Politiques 10.2.2 / 10.2.5 / 10.3)
- Mentionner clairement dans la description Store que ClipRoll propose au premier lancement (après validation de l'utilisateur dans l'assistant) de télécharger **Blender** (`download.blender.org`), **FFmpeg** (builds officiels) et le modèle **Whisper** (`Hugging Face`), tous vérifiés par empreinte **SHA-256** et stockés dans `%LOCALAPPDATA%\Clipoa\runtime`.
- Aucune mise à jour automatique externe n'est active dans la version Store (`core/updater.py` est automatiquement désactivé lorsque `CLIPOA_STORE_APP=1` ou que l'app tourne dans `WindowsApps`). Les mises à jour passent exclusivement par le Microsoft Store, sans jamais effacer ni retélécharger `%LOCALAPPDATA%\Clipoa`.
- L'application démarre et reste navigable même **hors ligne** (requis par la politique 10.3 pour les VM de certification Microsoft).

## 4. Point juridique à vérifier avant publication publique
- ClipRoll n'embarque ni Blender ni FFmpeg dans le `.msix`. Toutefois, les scripts Python `bpy` générés/exécutés dans Blender importent l'API `bpy` : faire valider ce point par un juriste avant commercialisation.

## 5. Checklist d'essai obligatoire sur un vrai PC / VM Windows avant soumission
- [ ] Générer un `.msix` signé localement (`build_msix.ps1 -Version 0.1.0 -SelfSign`), installer le certificat temporaire dans `Trusted People` et installer le `.msix`.
- [ ] Lancer ClipRoll depuis le Menu Démarrer : aucune fenêtre noire de terminal ne doit apparaître, le navigateur ouvre `http://localhost:8080`.
- [ ] Vérifier l'assistant de premier lancement : cliquer sur **Tout installer** → Blender, FFmpeg et Whisper se téléchargent dans `%LOCALAPPDATA%\Clipoa\runtime` avec vérification SHA-256.
- [ ] Vérifier l'icône dans la zone de notification (tray) : état du rendu, **Ouvrir ClipRoll**, **Quitter** (avec confirmation si un rendu est en cours).
- [ ] Lancer un court rendu 3D Blender + montage FFmpeg + sous-titres Whisper → vérifier la notification Windows « Vidéo prête ».
- [ ] Simuler une mise à jour MSIX (version `0.1.1`) → vérifier que `%LOCALAPPDATA%\Clipoa\storage` et `%LOCALAPPDATA%\Clipoa\runtime` (Blender/FFmpeg/Whisper) sont intacts et non retéléchargés.
- [ ] Désinstaller depuis Paramètres Windows → vérifier la suppression propre.
