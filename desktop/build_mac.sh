#!/bin/bash
# Builds desktop/dist/Stemmer.app (Apple Silicon).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"
MODELS="${STEMMER_MODELS:-$HOME/.cache/torch/hub/checkpoints}"

# Both Demucs models must be downloaded once so they can be bundled.
for model in htdemucs htdemucs_6s; do
  "$PY" -c "from demucs.pretrained import get_model; get_model('$model')" >/dev/null
done
ls "$MODELS"/*.th >/dev/null

(cd "$ROOT/frontend" && npm run build)

cd "$ROOT/desktop"
"$PY" -m PyInstaller --noconfirm --clean \
  --distpath "$ROOT/desktop/dist" --workpath "$ROOT/desktop/build" stemmer.spec

echo "Built $ROOT/desktop/dist/Stemmer.app ($(du -sh "$ROOT/desktop/dist/Stemmer.app" | cut -f1))"

# Drag-to-Applications disk image for the GitHub release.
VERSION=$(/usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" "$ROOT/desktop/dist/Stemmer.app/Contents/Info.plist")
DMG="$ROOT/desktop/dist/Stemmer-$VERSION-mac-arm64.dmg"
STAGE="$ROOT/desktop/build/dmg"
rm -rf "$STAGE" "$DMG" && mkdir -p "$STAGE"
cp -R "$ROOT/desktop/dist/Stemmer.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Stemmer $VERSION" -srcfolder "$STAGE" -fs HFS+ -format ULMO -ov "$DMG" >/dev/null
rm -rf "$STAGE"
echo "Built $DMG ($(du -sh "$DMG" | cut -f1))"
