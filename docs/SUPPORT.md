# Rapports de plantage et support

## Côté utilisateur
- Une fabrication échoue : la carte de la tâche affiche **Envoyer le rapport**.
- Une erreur hors fabrication (serveur, tâche de fond) : petite bulle en bas à gauche « ClipRoll a rencontré un problème » (Envoyer / Ignorer).
- Bouton **?** en haut à droite : **Contacter le support** (message obligatoire, e-mail facultatif).
- Rien ne part sans clic sur « Envoyer ». Le lien « Voir exactement ce qui sera envoyé » affiche le rapport complet.
- Si l'envoi échoue (hors ligne, relais non configuré), le rapport est gardé dans `storage/support/outbox/` et l'utilisateur peut le télécharger.

## Ce qui est masqué avant l'envoi (`core/crash_report.py`)
- Les valeurs exactes de tous les champs sensibles de `storage/*.json` (clés, jetons, mots de passe, cookies, proxy…), déchiffrées par le coffre puis retirées mot pour mot, quel que soit leur format (clé ElevenLabs comprise).
- Les variables d'environnement sensibles.
- Motifs connus : `sk-ant-…`, `sk_…`, `AIza…`, `ya29.…`, `Bearer …`, JWT, cookies, jetons opaques de 40+ caractères, e-mails, IP, nom d'utilisateur dans les chemins.
- Le relais refait un second nettoyage des motifs de clés.

## Côté Brice : réception (gratuit)
Le relais `oauth_relay_worker.js` reçoit les rapports sur `POST /support/report`.

1. Cloudflare → Workers KV → créer un namespace `clipoa-support`.
2. Worker `clipoa-oauth` → Settings → Bindings → KV namespace : nom **`SUPPORT_KV`** → `clipoa-support`.
3. Secret **`SUPPORT_ADMIN_TOKEN`** : une longue chaîne aléatoire (pour lire les rapports).
4. Facultatif, alerte immédiate sur le téléphone : secret **`SUPPORT_WEBHOOK_URL`** = URL d'un webhook Discord (serveur perso → salon → Intégrations → Webhooks).
5. Facultatif, plus tard avec un domaine : binding Send Email **`SUPPORT_EMAIL`** + variables `SUPPORT_EMAIL_FROM` / `SUPPORT_EMAIL_TO` (Email Routing, adresse de destination vérifiée).
6. Déployer `oauth_relay_worker.js`. Attention : la version déployée aujourd'hui est plus ancienne que ce fichier ; refaire un test de connexion TikTok après le déploiement.

Lire les rapports :
```bash
curl -H "Authorization: Bearer $SUPPORT_ADMIN_TOKEN" https://clipoa-oauth.clipoa-studio.workers.dev/support/reports
curl -H "Authorization: Bearer $SUPPORT_ADMIN_TOKEN" https://clipoa-oauth.clipoa-studio.workers.dev/support/reports/R-20261126-XXXXXXXX
```
Ou dans le tableau de bord Cloudflare (KV → `clipoa-support`). Les rapports expirent seuls après 90 jours (annoncé dans la page /privacy du relais).

Limites : 5 rapports par IP toutes les 10 minutes (mémoire de l'isolat, donc approximatif), 256 Ko max. Workers KV gratuit : 1 000 écritures par jour.
Adresse d'envoi côté app : `CLIPOA_SUPPORT_URL`, sinon `<relais OAuth>/support/report`.
