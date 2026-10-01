#!/usr/bin/env bash
# Build a macOS ScreenQuery.app and a drag-to-Applications DMG.
# Run this on a Mac. Windows builds use scripts/build-windows.ps1.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "scripts/build-dmg.sh builds a macOS .app and .dmg. Run it on a Mac." >&2
  echo "On Windows, run: powershell -ExecutionPolicy Bypass -File scripts\\build-windows.ps1" >&2
  exit 1
fi

cd "$(dirname "$0")/.."

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m pip install -r requirements-build.txt

mkdir -p build
python - <<'PY'
from pathlib import Path

from screenquery.icon_art import draw_icon

destination = Path("build/icon.png")
draw_icon(1024).save(destination)
PY

ICONSET="build/icon.iconset"
rm -rf "$ICONSET" build/icon.icns
mkdir -p "$ICONSET"
sips -z 16 16 build/icon.png --out "$ICONSET/icon_16x16.png" >/dev/null
sips -z 32 32 build/icon.png --out "$ICONSET/icon_16x16@2x.png" >/dev/null
sips -z 32 32 build/icon.png --out "$ICONSET/icon_32x32.png" >/dev/null
sips -z 64 64 build/icon.png --out "$ICONSET/icon_32x32@2x.png" >/dev/null
sips -z 128 128 build/icon.png --out "$ICONSET/icon_128x128.png" >/dev/null
sips -z 256 256 build/icon.png --out "$ICONSET/icon_128x128@2x.png" >/dev/null
sips -z 256 256 build/icon.png --out "$ICONSET/icon_256x256.png" >/dev/null
sips -z 512 512 build/icon.png --out "$ICONSET/icon_256x256@2x.png" >/dev/null
sips -z 512 512 build/icon.png --out "$ICONSET/icon_512x512.png" >/dev/null
sips -z 1024 1024 build/icon.png --out "$ICONSET/icon_512x512@2x.png" >/dev/null
iconutil -c icns "$ICONSET" -o build/icon.icns

python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name ScreenQuery \
  --icon build/icon.icns \
  --osx-bundle-identifier com.screenquery.ScreenQuery \
  --collect-submodules screenquery \
  --collect-submodules keyring \
  --collect-submodules pynput \
  --collect-submodules pystray \
  --hidden-import mss \
  --hidden-import PIL \
  screenquery/__main__.py

python - <<'PY'
import plistlib
from pathlib import Path

path = Path("dist/ScreenQuery.app/Contents/Info.plist")
with path.open("rb") as handle:
    info = plistlib.load(handle)
info["LSUIElement"] = True
info["CFBundleIdentifier"] = "com.screenquery.ScreenQuery"
info["NSScreenCaptureUsageDescription"] = (
    "ScreenQuery captures the full desktop when you press Shift+S+P "
    "so it can save a PNG or send the image to OpenAI."
)
with path.open("wb") as handle:
    plistlib.dump(info, handle)
PY

IDENTITY="${SIGN_IDENTITY:--}"
codesign --force --deep --options runtime \
  --entitlements scripts/entitlements.plist \
  --sign "$IDENTITY" \
  dist/ScreenQuery.app

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  ditto -c -k --keepParent dist/ScreenQuery.app dist/ScreenQuery.zip
  xcrun notarytool submit dist/ScreenQuery.zip \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait
  xcrun stapler staple dist/ScreenQuery.app
fi

STAGE="$(mktemp -d)"
cleanup() {
  if [[ -n "${STAGE:-}" ]]; then
    rm -rf "$STAGE"
  fi
}
trap cleanup EXIT
cp -R dist/ScreenQuery.app "$STAGE/ScreenQuery.app"
ln -s /Applications "$STAGE/Applications"
rm -f dist/ScreenQuery.dmg
hdiutil create \
  -volname ScreenQuery \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  dist/ScreenQuery.dmg

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  xcrun notarytool submit dist/ScreenQuery.dmg \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait
  xcrun stapler staple dist/ScreenQuery.dmg
fi

echo "Built dist/ScreenQuery.dmg"
