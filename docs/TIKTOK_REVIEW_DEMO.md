# Vidéo de démo pour la revue TikTok (Login Kit + Content Posting API)

La revue TikTok veut un **vrai enregistrement d'écran** du parcours complet, fait avec l'app en **Sandbox**. Une vidéo marketing ou générée sera refusée : la promo est un livrable à part.

## 1. Réglages à faire dans le portail TikTok (avant d'enregistrer)

| Réglage | Valeur conseillée | Pourquoi |
|---|---|---|
| Plateforme | **Desktop** (macOS) plutôt que Web | ClipRoll tourne en local (`127.0.0.1:8080`). En « Web », TikTok exige que le domaine visible dans la vidéo soit l'URL déclarée (`cliproll.app`) : impossible avec une app locale. En Desktop, la vidéo doit commencer par l'ouverture de l'app. À vérifier dans le portail que Desktop est proposé pour ces produits. |
| Website / Terms / Privacy | `https://cliproll.app`, `/terms.html`, `/privacy.html` | déjà en ligne |
| Produits | **Login Kit** + **Content Posting API** (Direct Post activé) | les seuls utilisés |
| Scopes | `user.info.basic`, `video.publish` | `video.upload` ne sert qu'au repli « brouillon » ; s'il reste coché il faut aussi le montrer. Le retirer, et retirer aussi `video.upload` de `scope` dans `oauth_relay_worker.js` (déploiement du Worker : accord de Brice). |
| Redirect URI | `<URL du relais>/oauth/tiktok/callback` | celle du Worker `clipoa-oauth` |
| Sandbox | compte test Docteur Shark **passé en privé** le temps de l'enregistrement | une app non auditée ne peut publier que sur un compte privé |

## 2. Ce que l'app montre maintenant (branche `claude/project-thread-b80lyc`)

Panneau TikTok dans « Publier » quand TikTok est sélectionné, conforme aux règles Direct Post :
nom + avatar du compte (`creator_info`), visibilité **sans valeur par défaut** (options données par TikTok), cases Commenter / Duo / Collage décochées et grisées si le compte les a coupées, déclaration du contenu commercial (« Ta marque » / « Contenu de marque », « Moi uniquement » interdit pour le contenu de marque), texte de consentement avec lien vers la *Music Usage Confirmation* (et la *Branded Content Policy*), contrôle de la durée max, bouton bloqué tant que les choix ne sont pas faits.

## 3. Script d'enregistrement (2 à 3 min, plein écran, 1080p)

L'interface est en français : ajouter des sous-titres ou une voix off **en anglais** au montage (voix ElevenLabs possible).

1. **0:00** Bureau du Mac, ouvrir ClipRoll (icône du Dock). Voix : « ClipRoll is a desktop app that creates short videos and posts them to TikTok. »
2. **0:10** Onglet Connexions → TikTok → « Se connecter ». La page officielle TikTok s'ouvre : laisser 3 s sur le nom de l'app et la liste des autorisations. Se connecter avec le compte **Sandbox**, cliquer Autoriser.
3. **0:35** Retour dans ClipRoll : le compte TikTok apparaît connecté avec son nom (scope `user.info.basic`).
4. **0:45** Fabrique : lancer ou ouvrir une vidéo (couper l'attente au montage). Lire 3 s de la vidéo.
5. **1:05** Publier : choisir la vidéo, sélectionner TikTok. Montrer le panneau : nom/avatar du compte, ouvrir la liste de visibilité et choisir, cocher une interaction, activer puis désactiver « Divulguer le contenu commercial » pour montrer les libellés, pointer le texte de consentement. Remplir le titre.
6. **1:40** Maintenir « Publier ». Montrer le statut « Envoyé » dans le calendrier (scope `video.publish`).
7. **1:55** Ouvrir TikTok (téléphone filmé ou tiktok.com) sur le profil du compte test : la vidéo est là.
8. **2:10** Fin (optionnel : déconnecter le compte dans Connexions).

## 4. Exporter en moins de 50 Mo

Enregistrer avec QuickTime (Fichier → Nouvel enregistrement de l'écran), puis :

```bash
ffmpeg -i demo.mov -vf "scale=1920:-2" -c:v libx264 -crf 28 -preset slow -c:a aac -b:a 128k demo_tiktok.mp4
```

À ~2 min, ce réglage donne en général 15 à 40 Mo. Si c'est trop gros, monter `-crf` à 30.
