#!/usr/bin/env bash
# DMG de Clipoa pour la vente publique : app signée Developer ID, notarisée par Apple et « staplée ».
#   packaging/build_dmg.sh <version>            → signature locale seulement (essai, sans compte Apple)
#   CLIPOA_SIGN_ID="Developer ID Application: Prénom Nom (TEAMID)" CLIPOA_NOTARY_PROFILE=clipoa packaging/build_dmg.sh <version>
# Préparer une fois le profil de notarisation (mot de passe d'app sur appleid.apple.com) :
#   xcrun notarytool store-credentials clipoa --apple-id <email> --team-id <TEAMID> --password <mot-de-passe-app>
# Prérequis : dist/install.sh fabriqué par build_release.sh (il contient l'adresse des versions).
# L'app ne contient que le lanceur : au 1er lancement elle installe Clipoa, Blender, etc. dans ~/Library/Clipoa,
# puis les mises à jour passent par le bouton « Mettre à jour » sans re-télécharger le DMG.
set -euo pipefail

VERSION="${1:?usage: build_dmg.sh <version>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"
SIGN_ID="${CLIPOA_SIGN_ID:--}"
PROFILE="${CLIPOA_NOTARY_PROFILE:-}"
[ -f "$DIST/install.sh" ] || { echo "lance d'abord packaging/build_release.sh" >&2; exit 2; }
grep -q "__CLIPOA_UPDATE_URL__" "$DIST/install.sh" && { echo "dist/install.sh sans adresse de versions" >&2; exit 2; }

B="$(mktemp -d /tmp/clipoa_dmg.XXXX)"
APP="$B/stage/Clipoa.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "▸ Lanceur"
clang -O2 -arch arm64 -mmacosx-version-min=12.0 -o "$APP/Contents/MacOS/Clipoa" "$ROOT/packaging/macos/launcher.c"
cp "$ROOT/packaging/macos/bootstrap.sh" "$DIST/install.sh" "$APP/Contents/Resources/"
chmod +x "$APP/Contents/Resources/"*.sh
[ -f "$ROOT/assets/clipoa.icns" ] && cp "$ROOT/assets/clipoa.icns" "$APP/Contents/Resources/clipoa.icns"
cat > "$APP/Contents/Info.plist" <<EOS
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Clipoa</string>
  <key>CFBundleDisplayName</key><string>Clipoa</string>
  <key>CFBundleIdentifier</key><string>app.clipoa.desktop</string>
  <key>CFBundleExecutable</key><string>Clipoa</string>
  <key>CFBundleIconFile</key><string>clipoa</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>LSArchitecturePriority</key><array><string>arm64</string></array>
  <key>LSUIElement</key><true/>
</dict></plist>
EOS

echo "▸ Signature ($([ "$SIGN_ID" = "-" ] && echo "locale, essai" || echo "$SIGN_ID"))"
if [ "$SIGN_ID" = "-" ]; then
  codesign --force --sign - "$APP"
else
  codesign --force --options runtime --timestamp --sign "$SIGN_ID" "$APP"
fi
codesign --verify --strict --verbose=2 "$APP"

echo "▸ DMG"
ln -s /Applications "$B/stage/Applications"
DMG="$DIST/Clipoa-$VERSION.dmg"
rm -f "$DMG"
hdiutil create -quiet -volname "Clipoa" -srcfolder "$B/stage" -fs HFS+ -format UDZO -ov "$DMG"
[ "$SIGN_ID" = "-" ] || codesign --force --timestamp --sign "$SIGN_ID" "$DMG"

if [ -n "$PROFILE" ] && [ "$SIGN_ID" != "-" ]; then
  echo "▸ Notarisation par Apple (quelques minutes)"
  xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
  spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG"
else
  echo "  (pas de notarisation : CLIPOA_SIGN_ID et CLIPOA_NOTARY_PROFILE non fournis — DMG d'essai seulement)"
fi
rm -rf "$B"
echo "✓ $DMG ($(du -h "$DMG" | cut -f1))"
