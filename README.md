# ScreenQuery

ScreenQuery is a menu-bar utility for Windows and macOS. Hold **Shift** and press **S** and **P** together to capture the full desktop. It can save a PNG, send the image to an OpenAI vision model, or both, then show the result in a floating status window.

It is one Python application, packaged the same way EyesRhythm ships both platforms from one project: a Windows `.exe` and a macOS `.dmg`. A native Xcode app would only run on a Mac.

The app ships with no API key. Paste your own in Settings. It is stored in the system keychain (macOS Keychain or Windows Credential Manager), never in `settings.json` and never in this repository.

## Requirements

- Windows 10 or later, or macOS 12 or later
- Python 3.10 or later, with Tk (included in the official Windows and python.org macOS installers)
- An OpenAI API key only if you turn on **Send to OpenAI**

## Run

From the repository root:

```bash
python -m venv .venv
```

Windows:

```bat
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m screenquery
```

macOS:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m screenquery
```

`python -m screenquery --check` prints the version and does not open a window.

On macOS the menu title is **SQ** (no Dock icon when PyObjC is installed). On Windows the icon sits in the system tray. The first launch opens Settings. Later launches open Settings only when the tray icon could not be created.

**Capture Now** in the menu runs the same path without the hotkey.

## Hotkey

Hold Shift, then press S and P (either letter first). The chord fires once until you release S or P. Releasing Shift cancels a partial chord. Key repeat does not capture again. Caps Lock does not count as Shift.

The listener only observes keys. It does not swallow them, so S and P still reach the app in front.

## Permissions

| System | What to grant | Why |
| --- | --- | --- |
| macOS | **Screen Recording** | Capture the display |
| macOS | **Input Monitoring** | Global Shift+S+P hotkey. Allow **Accessibility** too if macOS lists the prompt there |
| Windows | No privacy pane | The hotkey is a global keyboard hook |

macOS ties each grant to the exact program. A copy started from a terminal and `ScreenQuery.app` from the DMG are different apps. After you allow access, quit ScreenQuery and open it again.

The packaged Mac app declares `NSScreenCaptureUsageDescription`. Use **Settings → Permissions** to jump to Screen Recording, Input Monitoring, or Accessibility. If PyObjC Quartz is installed, Settings can also request Screen Recording and Input Monitoring directly.

Windows has no equivalent prompt. If Shift+S+P does nothing, another program may already own that chord. **Capture Now** still works.

## Settings

From the menu: **Settings…**

- **Save screenshot** and **Send to OpenAI** are independent. Enable one or both. Both start out as save on, OpenAI off.
- **Save location**
  - Default: `~/ScreenQuery/<YYYY-MM-DD>/ScreenQuery-<yyyyMMdd-HHmmss-SSS>.png`
  - Custom folder: PNGs are written directly in the folder you pick (no extra date directory).
  - If that filename already exists, ScreenQuery appends `-2`, `-3`, and so on.
- **OpenAI**
  - Paste a key and choose **Save Key**. The item is service `com.screenquery.ScreenQuery`, account `openai-api-key`. **Remove Key** deletes it.
  - Base URL defaults to `https://api.openai.com/v1`. The client posts to `<base>/chat/completions`. `https://api.openai.com` is normalized to the `/v1` endpoint. A full `…/chat/completions` URL is used as-is. `http` is rejected except for `localhost` / `127.0.0.1`. Userinfo in the URL is stripped.
  - Model defaults to `gpt-4o`. `gpt-4o-mini` and `gpt-4.1` are shortcuts; any Chat Completions vision model name is accepted.
- **Launch at login** writes a LaunchAgent (`com.screenquery.ScreenQuery`) on macOS, or an `HKCU\...\Run` value named `ScreenQuery` on Windows.

Preferences live in:

- macOS: `~/Library/Application Support/ScreenQuery/settings.json`
- Windows: `%APPDATA%\ScreenQuery\settings.json`

If a key was ever written into that file, ScreenQuery removes it on the next load. If both actions are off, the hotkey does not capture; the status window tells you to turn one on.

## What a capture does

1. Hides the status window, then captures every display as one image (the cursor is included). The Settings window can still appear in the shot if it is open.
2. If save is on, writes a full PNG to the folder above.
3. If OpenAI is on, the status window says it is asking, then downscales the long edge to at most 2048 pixels, JPEG-compresses the image (about 4.5 MB or smaller), and sends a Chat Completions request. The prompt asks the model to answer or explain whatever is on screen. The key is sent only as a Bearer token. If a model rejects `max_tokens`, ScreenQuery retries once with `max_completion_tokens`. A save error does not cancel the OpenAI request.
4. Shows a borderless, always-on-top window at the bottom-right of the primary screen. On macOS it is a non-activating help window. It reports the save path and the model reply, or a short error. It dismisses on its own (about 8 seconds for a save, 12 for an error, 20 for an answer), waits while the pointer is over it or while OpenAI is still responding, and closes if you click the title or ✕. **Copy** copies the answer. **Show in Folder** reveals the PNG.

## Tests

The tests use only the Python standard library:

```bash
python -m unittest discover -s tests -v
```

They cover the Shift+S+P state machine, default and custom save paths, Chat Completions URL and JSON construction (the API key is not part of the body), response parsing, the `max_tokens` retry, keychain round-trip, leaked-key removal, and launch-item text.

## Build a Windows exe

On Windows, from the repository root:

```bat
powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1
```

The script installs the build dependencies and writes a windowed one-file `dist\ScreenQuery.exe`.

## Build a DMG

On a Mac, from the repository root:

```bash
chmod +x scripts/build-dmg.sh
./scripts/build-dmg.sh
```

The script runs PyInstaller `--windowed`, marks the app as an agent (`LSUIElement`), ad-hoc signs it with Hardened Runtime, and packs `dist/ScreenQuery.app` plus an Applications alias into `dist/ScreenQuery.dmg`.

`scripts/build-dmg.sh` exits immediately on any system that is not macOS. This repository can be unit-tested on Linux, but the DMG and the exe have to be built on the matching OS.

Sign with a Developer ID certificate and notarize when you distribute outside your own Mac:

```bash
SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
NOTARY_PROFILE="your-notarytool-keychain-profile" \
./scripts/build-dmg.sh
```

Create the notary profile once with `xcrun notarytool store-credentials`. The script submits the app, staples the ticket, builds the DMG, then submits the DMG. The app is not sandboxed: a global hotkey and a user-chosen save folder do not fit the App Sandbox. `scripts/entitlements.plist` only relaxes library validation so a notarized PyInstaller binary can start.

## Privacy

The screenshot stays on the machine unless **Send to OpenAI** is on. In that case the JPEG is posted to the base URL you configured, with your keychain key as a Bearer token. Preferences store the toggles, folder path, base URL, and model name.

## Project layout

- `screenquery/` — hotkey, capture, keychain, settings, overlay, tray
- `tests/` — standard-library unit tests
- `scripts/build-dmg.sh` — macOS app and DMG
- `scripts/build-windows.ps1` — Windows executable
- `scripts/entitlements.plist` — hardened-runtime exceptions for the Mac build

## Follow-ups

- Run the app on a real Windows PC and a real Mac, including save only, OpenAI only, and both.
- Confirm the macOS Screen Recording and Input Monitoring prompts, then quit and reopen that same binary.
- Notarize with an Apple Developer ID before sharing the DMG.
