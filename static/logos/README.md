# Logos des services (ClipRoll)

Logos officiels (vectoriels, tracés Simple Icons, couleurs officielles des marques). Chaque logo existe en
couleur (`<clé>.svg`) et en blanc (`<clé>-white.svg`) pour les fonds sombres.

Règles d'usage (chartes des plateformes) : ne pas déformer, recolorer, faire pivoter ni animer un logo ;
garder ses proportions et un espace libre autour ; n'utiliser que la couleur officielle, le noir ou le blanc.
YouTube : le triangle « play » reste blanc sur le rouge (ajouté dans `youtube.svg` et `youtubeshorts.svg`).

Le macro `brand()` de `templates/index.html` affiche la version blanche en thème sombre pour les logos
noirs (TikTok, Anthropic, Apple). Tant qu'un fichier manque (ex. `facebook.svg`, `elevenlabs.svg`),
ClipRoll affiche une pastille de couleur avec l'initiale. `.png` est aussi accepté (même nom).
