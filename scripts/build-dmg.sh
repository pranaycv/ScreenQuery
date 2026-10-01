#!/usr/bin/env bash
# Build ScreenQuery.app and pack a drag-to-Applications disk image.
# Run this on macOS. xcodebuild and hdiutil ship with Xcode / macOS.
# If create-dmg is installed it is used first; hdiutil is the fallback.

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: scripts/build-dmg.sh must be run on macOS." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="$ROOT/ScreenQuery.xcodeproj"
SCHEME="ScreenQuery"
CONFIG="${CONFIGURATION:-Release}"
DERIVED="$ROOT/build/DerivedData"
DIST="$ROOT/dist"
SIGN_IDENTITY="${CODE_SIGN_IDENTITY:--}"

if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "error: xcodebuild not found. Install Xcode, then run: xcode-select -s /Applications/Xcode.app" >&2
  exit 1
fi

echo "Building ${SCHEME} (${CONFIG})…"
xcodebuild \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration "$CONFIG" \
  -destination "generic/platform=macOS" \
  -derivedDataPath "$DERIVED" \
  ONLY_ACTIVE_ARCH=NO \
  CODE_SIGN_STYLE=Manual \
  "CODE_SIGN_IDENTITY=${SIGN_IDENTITY}" \
  CODE_SIGNING_ALLOWED=YES \
  CODE_SIGNING_REQUIRED=YES \
  AD_HOC_CODE_SIGNING_ALLOWED=YES \
  build

APP="$DERIVED/Build/Products/${CONFIG}/ScreenQuery.app"
if [[ ! -d "$APP" ]]; then
  echo "error: built app not found at:" >&2
  echo "  $APP" >&2
  find "$DERIVED" -name 'ScreenQuery.app' -print >&2 || true
  exit 1
fi

mkdir -p "$DIST"
DMG="$DIST/ScreenQuery.dmg"
rm -f "$DMG"

if [[ -d /Volumes/ScreenQuery ]]; then
  hdiutil detach "/Volumes/ScreenQuery" -quiet || true
fi

if command -v create-dmg >/dev/null 2>&1; then
  STAGING="$(mktemp -d "${TMPDIR:-/tmp}/screenquery-dmg.XXXXXX")"
  cp -R "$APP" "$STAGING/ScreenQuery.app"
  echo "Packing with create-dmg…"
  if create-dmg \
    --volname "ScreenQuery" \
    --window-pos 200 120 \
    --window-size 640 400 \
    --icon-size 128 \
    --icon "ScreenQuery.app" 160 170 \
    --hide-extension "ScreenQuery.app" \
    --app-drop-link 470 170 \
    "$DMG" \
    "$STAGING"
  then
    rm -rf "$STAGING"
    echo "Created $DMG"
    exit 0
  fi
  echo "create-dmg failed; falling back to hdiutil." >&2
  rm -rf "$STAGING"
  rm -f "$DMG"
fi

STAGING="$ROOT/build/dmg-staging"
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/ScreenQuery.app"
ln -s /Applications "$STAGING/Applications"

echo "Packing with hdiutil…"
hdiutil create \
  -volname "ScreenQuery" \
  -srcfolder "$STAGING" \
  -ov \
  -format UDZO \
  "$DMG"

echo "Created $DMG"
echo "Open the image and drag ScreenQuery.app to Applications."
