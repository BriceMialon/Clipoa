# ClipRoll — Pack Complet à intégrer (Handoff pour Claude)

Dossier source sur la machine : `/Users/brice/Downloads/gemini agent/cliproll-brand/`

## 1. Renommage & Domaine
- **Nom** : `ClipRoll` (remplace `Clipoa`)
- **Domaine principal** : `cliproll.app` (secondaires libres : `cliproll.ai`, `cliproll.fr`, `getcliproll.com`)

## 2. Icônes finales (Logo 4 — Creator Roll & Spark)
- **macOS (app + DMG)** :
  - `icons/macos/ClipRoll.icns` — vrai `.icns` multi-tailles (16→1024 px @1x/@2x) avec squircle HIG Apple + marge + ombre douce.
  - `icons/macos/ClipRoll-macOS-1024.png` — PNG 1024×1024 transparent avec squircle.
- **Windows (exe / installer / Microsoft Store)** :
  - `icons/windows/ClipRoll.ico` — vrai `.ico` multi-tailles (16, 24, 32, 48, 64, 128, 256 px).
  - `icons/windows/ClipRoll-Store-1024.png` — PNG 1024×1024 plein bord pour le Store.
  - `icons/windows/icon-{16,24,32,48,64,128,256,512}.png` — tailles unitaires prêtes à l'emploi.
- **Web / UI** :
  - `icons/web/favicon.ico`, `favicon-16x16.png`, `favicon-32x32.png`, `apple-touch-icon.png`, `icon-192.png`, `icon-512.png`.

## 3. Vrais logos vectoriels officiels (remplace le faux logo YouTube actuel)
Dossier `logos-plateformes/` (chaque logo existe en couleur officielle + version `-white.svg` pour fond sombre) :
- `youtube.svg` / `youtube-white.svg`
- `youtubeshorts.svg` / `youtubeshorts-white.svg`
- `tiktok.svg` / `tiktok-white.svg`
- `instagram.svg` / `instagram-white.svg`
- `facebook.svg` / `facebook-white.svg`
- `claude.svg` / `claude-white.svg`
- `elevenlabs.svg` / `elevenlabs-white.svg`
- `anthropic.svg` / `anthropic-white.svg`
- `googlegemini.svg` / `googlegemini-white.svg`
- `stripe.svg` / `stripe-white.svg`
- `apple.svg` & `windows.svg` / `windows-white.svg`

## 4. Direction Artistique, Boutons Spéciaux & Mini-Icônes UI
- `design-system.css` : variables CSS (`#0B0B16`, `#101022`, `#15152B`, `#00E5FF`, `#FF3B5C`), boutons spéciaux (`.cr-btn-spark` CTA corail avec reflet + étincelle animée, `.cr-btn-cyan` export néon, `.cr-btn-pro` bordure dégradée cyan→corail, `.cr-btn-platform`), badges (`.cr-badge-ai`, `.cr-badge-live`), barre de progression IA (`.cr-progress`), carte 9:16 (`.cr-phone-916`).
- `icons-ui/cliproll-ui-icons.svg` : sprite SVG 24×24 cohérent avec la DA (`#cr-mark`, `#cr-spark`, `#cr-vertical`, `#cr-voice`, `#cr-captions`, `#cr-export`, `#cr-cut`, `#cr-script`).
- `design-system-preview.html` : page d'aperçu visuel complète (à ouvrir dans le navigateur pour voir tous les boutons, couleurs, logos et icônes en vrai).
