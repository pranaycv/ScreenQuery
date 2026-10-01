# ScreenQuery

ScreenQuery is a macOS menu-bar app. Press **Shift+S+P** (Shift held, S and P down together) to capture the full screen. It can save a PNG, send the image to an OpenAI-compatible vision model, or both. A transparent status window reports the saved path and the model’s answer without activating the app.

This repository builds on macOS. The agent environment used to write it is Linux, so the Xcode project and DMG script are included, but a signed `.dmg` was not produced here.

## Requirements

- macOS 14 Sonoma or later
- Xcode 15 or later

## Run

1. Open `ScreenQuery.xcodeproj` and select the **ScreenQuery** scheme.
2. Run. The app is a menu-bar utility (`LSUIElement`): a viewfinder item appears, and there is no Dock icon.
3. Grant the permissions below. If capture or the hotkey still fails, quit and reopen the app.
4. Open **Settings…** from the menu bar to choose what the hotkey does.

The project ad-hoc signs the app (`CODE_SIGN_IDENTITY = -`) so it runs without an Apple Developer account. Ad-hoc identities change every rebuild, so macOS may ask for permissions again after each build.

## Hotkey

**Shift + S + P**, as letters on the active keyboard layout. All three must be down at once. The chord fires once per press and does not repeat until you release a key. It is a listen-only event tap, so the keys are not swallowed and can still be typed into the focused app.

The same capture is available from the menu as **Capture Screen**.

## Permissions

macOS ties each grant to the code signature of the specific copy you are running. A build from Xcode and a copy in `/Applications` are different. After replacing the app, remove the old ScreenQuery entry in System Settings and enable the new one. You often need to quit and reopen after granting access.

| Permission | Why | Where |
| --- | --- | --- |
| **Screen Recording** | Capture the display with ScreenCaptureKit. | System Settings → Privacy & Security → Screen Recording |
| **Input Monitoring** | Observe the global Shift+S+P chord while another app is focused. | System Settings → Privacy & Security → Input Monitoring |
| **Accessibility** | Some macOS versions require this as well as Input Monitoring for global key events. | System Settings → Privacy & Security → Accessibility |

Settings lists the current status of each permission, with **Grant** and **System Settings** buttons. **Recheck** restarts the hotkey monitor. The first capture prompts for Screen Recording if it has not been decided yet.

`NSScreenCaptureUsageDescription` in `Info.plist` is the text macOS shows for screen capture.

## Settings

Any combination of the two actions is valid. Both off means the hotkey only shows a reminder.

- **Save screenshot** (on by default). Writes a unique PNG named like `ScreenQuery-20261001-223507-123.png`.
  - **Default folder:** `~/ScreenQuery/<YYYY-MM-DD>/`
  - **Chosen folder:** the directory you pick, with no date subfolder. The choice is stored as a path and a security-scoped bookmark.
- **Send to LLM** (off until you configure it). Posts the screenshot to an OpenAI-compatible `chat/completions` endpoint. Set the base URL (default `https://api.openai.com/v1`), model (default `gpt-4o`), and the instruction prompt. The model must accept images. `http://localhost` and other local hosts are allowed; public hosts still need HTTPS.
- **API key.** Paste it in Settings and choose **Save to Keychain**. It is stored in the login Keychain (`service` `com.screenquery.app`, `account` `llm-api-key`) and is not written to UserDefaults. There is no key in this repository.
- **Overlay dismiss.** How long the status window stays up after the work finishes (default 12 seconds). It stays open while the pointer is over it. Click the window or the close button to dismiss it sooner.

The screenshot is sent only to the endpoint you configure.

## Status overlay

After the hotkey, a non-activating floating panel appears on the screen under the pointer, including over full-screen spaces. It reports:

- the saved path, abbreviated with `~`, and a **Show** button
- the model response when it arrives, with **Copy**
- a short error if capture, saving, or the request fails

The panel background is clear. Its window is excluded from screen capture (`sharingType = .none`), and ScreenQuery’s own windows are omitted from the shot.

Multiple displays are captured and stitched into one PNG using each display’s frame. A single display is saved as captured.

## Build a DMG

On a Mac, from the repository root:

```bash
chmod +x scripts/build-dmg.sh
./scripts/build-dmg.sh
```

The script runs `xcodebuild` (Release, universal when the SDK allows it) and writes `dist/ScreenQuery.dmg`. Open the image and drag **ScreenQuery** to **Applications**.

It uses [`create-dmg`](https://github.com/create-dmg/create-dmg) when that tool is on `PATH`, and otherwise `hdiutil`. Override the configuration or signature if you need to:

```bash
CONFIGURATION=Debug ./scripts/build-dmg.sh
CODE_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" ./scripts/build-dmg.sh
```

Equivalent build without the script:

```bash
xcodebuild \
  -project ScreenQuery.xcodeproj \
  -scheme ScreenQuery \
  -configuration Release \
  -destination "generic/platform=macOS" \
  ONLY_ACTIVE_ARCH=NO \
  build
```

The `.app` is under the derived data `Build/Products/Release/` directory.

An ad-hoc signed app downloaded from the internet may be blocked by Gatekeeper. For a local copy, right-click the app, choose **Open**, or clear the quarantine flag:

```bash
xattr -dr com.apple.quarantine /Applications/ScreenQuery.app
```

## Signing and notarization

The DMG script does not notarize. For distribution outside your own Mac:

1. Enroll in the Apple Developer Program and create a Developer ID Application certificate.
2. In Xcode, set the team and use that certificate instead of the ad-hoc identity. Keep Hardened Runtime on. The app is intentionally not sandboxed: a global event tap and ScreenCaptureKit are more reliable that way for a Developer ID utility.
3. Sign the app, then notarize and staple:

```bash
codesign --deep --force --options runtime --timestamp \
  --entitlements ScreenQuery/ScreenQuery.entitlements \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  ScreenQuery.app

xcrun notarytool submit dist/ScreenQuery.dmg \
  --apple-id "you@example.com" --team-id TEAMID --password "app-specific-password" \
  --wait
xcrun stapler staple dist/ScreenQuery.dmg
```

Sign the app before you put it in the disk image. Notarization was not run for this repository.

## Tests

Chord detection, screenshot paths, and response parsing live in `ScreenQuery/Core` and do not import AppKit. From the repository root:

```bash
swift test
```

The Xcode app target compiles those same files into the app. `swift test` does not build the menu-bar app.

## Layout

- `ScreenQuery/App` — menu bar, capture flow
- `ScreenQuery/Hotkey` — Shift+S+P event tap
- `ScreenQuery/Capture` — ScreenCaptureKit, PNG save
- `ScreenQuery/LLM` — OpenAI-compatible vision request
- `ScreenQuery/Security` — Keychain
- `ScreenQuery/Settings` — preferences window
- `ScreenQuery/Permissions` — Screen Recording, Accessibility, Input Monitoring
- `ScreenQuery/Overlay` — floating status panel
- `scripts/build-dmg.sh` — Release `.app` and `.dmg`

## Follow-ups

- Run the app on a Mac and confirm the permission prompts, multi-display stitch, overlay on a full-screen space, and a real vision response.
- Developer ID sign and notarize before sharing the DMG.
- Ad-hoc signatures change when the binary changes, so TCC prompts repeat during development.
