"""Permission copy shown in Settings. macOS TCC checks live in the UI layer."""

from __future__ import annotations


def permission_help(platform: str) -> str:
    if platform == "darwin":
        return (
            "macOS needs Screen Recording to capture the display, and Input Monitoring "
            "for the global Shift+S+P hotkey. If that hotkey prompt is listed under "
            "Accessibility, allow it there too. A copy started from a terminal and an "
            "installed .app are different apps to macOS. After you allow access, quit "
            "ScreenQuery and open it again."
        )
    if platform == "win32":
        return (
            "Windows does not use macOS Screen Recording or Input Monitoring prompts. "
            "The hotkey is a global keyboard hook. If Shift+S+P does nothing, "
            "another app may already be using that chord. Capture Now in the menu still works."
        )
    return (
        "On this system, capture uses the screen API and the hotkey uses a keyboard hook. "
        "Grant screen access if the desktop environment asks for it."
    )


MAC_SETTINGS_URLS = {
    "screen": (
        "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ScreenCapture",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    ),
    "input": (
        "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ListenEvent",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
    ),
    "accessibility": (
        "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Accessibility",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    ),
}
