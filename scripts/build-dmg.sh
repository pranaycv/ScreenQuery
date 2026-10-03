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
  PYTHON_BIN="${PYTHON:-}"
  if [[ -z "$PYTHON_BIN" ]]; then
    if command -v python3.12 >/dev/null 2>&1 && python3.12 -c "import tkinter" >/dev/null 2>&1; then
      PYTHON_BIN="python3.12"
    else
      PYTHON_BIN="python3"
    fi
  fi
  "$PYTHON_BIN" -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m pip install -r requirements-build.txt
python -c "import sys, tkinter; print(sys.executable, sys.version)" || {
  echo "This Python has no Tk, so the Mac app cannot open its window." >&2
  echo "Install a Python that includes Tk: brew install python-tk@3.12" >&2
  exit 1
}

if [[ ! -f frontend/dist/index.html ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "frontend/dist is missing. In frontend/, run: npm ci && npm run build" >&2
    exit 1
  fi
  (cd frontend && npm ci && npm run build)
fi

mkdir -p build
python - <<'PY'
from pathlib import Path

from screenquery.icon_art import draw_icon

Path("build/icon.png").parent.mkdir(parents=True, exist_ok=True)
draw_icon(1024).save("build/icon.png")
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

IDENTITY="${SIGN_IDENTITY:--}"
python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name ScreenQuery \
  --icon build/icon.icns \
  --osx-bundle-identifier com.screenquery.ScreenQuery \
  --codesign-identity "$IDENTITY" \
  --osx-entitlements-file scripts/entitlements.plist \
  --collect-submodules screenquery \
  --collect-submodules keyring \
  --collect-submodules pynput \
  --collect-submodules pystray \
  --hidden-import mss \
  --hidden-import PIL \
  --hidden-import AppKit \
  --hidden-import Foundation \
  --hidden-import objc \
  --hidden-import Quartz \
  --hidden-import keyring.backends.macOS \
  --hidden-import pynput.keyboard._darwin \
  --hidden-import pystray._darwin \
  --hidden-import webview \
  --hidden-import webview.platforms.cocoa \
  --add-data "frontend/dist:frontend/dist" \
  screenquery/__main__.py

python - <<'PY'
import plistlib
from pathlib import Path

path = Path("dist/ScreenQuery.app/Contents/Info.plist")
with path.open("rb") as handle:
    info = plistlib.load(handle)
info["LSUIElement"] = True
info["CFBundleIdentifier"] = "com.screenquery.ScreenQuery"
info["CFBundleShortVersionString"] = "1.0.0"
info["NSScreenCaptureUsageDescription"] = (
    "ScreenQuery captures the full desktop when you press Shift+S+P "
    "so it can save a PNG or send the image to OpenAI."
)
with path.open("wb") as handle:
    plistlib.dump(info, handle)
PY

# Info.plist changed after PyInstaller signed the bundle. Re-sign the
# outer bundle only so the inner Mach-O signatures stay intact.
SIGN_ARGS=(--force --options runtime --entitlements scripts/entitlements.plist --sign "$IDENTITY")
if [[ "$IDENTITY" != "-" ]]; then
  SIGN_ARGS+=(--timestamp)
fi
codesign "${SIGN_ARGS[@]}" dist/ScreenQuery.app
codesign --verify --verbose=2 dist/ScreenQuery.app

echo "Smoke test"
python - <<'PY'
import os
import subprocess
import sys
import tempfile
from pathlib import Path

descriptor, name = tempfile.mkstemp(prefix="screenquery-check-")
os.close(descriptor)
marker = Path(name)
env = os.environ.copy()
env["SCREENQUERY_CHECK_FILE"] = str(marker)
try:
    result = subprocess.run(
        ["dist/ScreenQuery.app/Contents/MacOS/ScreenQuery", "--check"],
        timeout=45,
        capture_output=True,
        text=True,
        env=env,
    )
except subprocess.TimeoutExpired:
    sys.exit("ScreenQuery --check did not exit. The frozen app did not start.")
print(result.stdout)
print(result.stderr, file=sys.stderr)
if result.returncode != 0:
    sys.exit(result.returncode)
text = marker.read_text(encoding="utf-8") if marker.exists() else ""
marker.unlink(missing_ok=True)
if "ScreenQuery" not in text:
    sys.exit("ScreenQuery --check exited without writing its version.")
print(text.strip())
PY

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  ditto -c -k --keepParent dist/ScreenQuery.app dist/ScreenQuery.zip
  xcrun notarytool submit dist/ScreenQuery.zip \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait
  xcrun stapler staple dist/ScreenQuery.app
  rm -f dist/ScreenQuery.zip
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
cat > "$STAGE/How to Open.txt" <<'EOF'
ScreenQuery

1. Drag ScreenQuery onto the Applications folder.
2. Eject this disk image.
3. In Applications, Control-click ScreenQuery and choose Open, then Open again.
   This test build is not notarized, so macOS warns the first time.
4. If macOS says the app is damaged, run this in Terminal, then open it again:

   xattr -dr com.apple.quarantine /Applications/ScreenQuery.app

5. Settings opens in front. The menu-bar title is SQ.
6. Allow Screen Recording and Input Monitoring, quit ScreenQuery, and open it again.
7. Hold Shift and press S and P together.
EOF
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
