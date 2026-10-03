"""Launch-at-login helpers for Windows and macOS.

The functions that build the plist or Run-key value are pure. Writing them
to the machine happens only from the settings window.
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

LABEL = "com.screenquery.ScreenQuery"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_VALUE_NAME = "ScreenQuery"


def macos_launch_agent_path(home: Path | None = None) -> Path:
    root = home or Path.home()
    return root / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def launch_command() -> list[str]:
    """How to start ScreenQuery again at login.

    On macOS the installed app is one TCC identity. A login item that runs
    the virtualenv Python is a second binary, so Screen Recording approval
    does not carry over.
    """
    if sys.platform == "darwin":
        installed = Path("/Applications/ScreenQuery.app/Contents/MacOS/ScreenQuery")
        if installed.is_file():
            return [str(installed)]
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "screenquery"]


def macos_plist(program: list[str] | str) -> str:
    args = [program] if isinstance(program, str) else list(program)
    items = "\n".join(f"\t\t<string>{escape(arg)}</string>" for arg in args)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>{LABEL}</string>
	<key>ProgramArguments</key>
	<array>
{items}
	</array>
	<key>RunAtLoad</key>
	<true/>
</dict>
</plist>
"""


def windows_run_value(executable: list[str] | str) -> str:
    args = [executable] if isinstance(executable, str) else list(executable)
    return " ".join(f'"{part}"' for part in args)


def launch_at_login_supported() -> bool:
    return sys.platform in {"darwin", "win32"}


def is_enabled() -> bool:
    if sys.platform == "darwin":
        return macos_launch_agent_path().is_file()
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
                winreg.QueryValueEx(key, WINDOWS_VALUE_NAME)
            return True
        except OSError:
            return False
    return False


def set_enabled(enabled: bool, command: list[str] | str | None = None) -> None:
    program = launch_command() if command is None else command
    if sys.platform == "darwin":
        path = macos_launch_agent_path()
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(macos_plist(program), encoding="utf-8")
            _launchctl_load(path)
        else:
            _launchctl_unload(path)
            path.unlink(missing_ok=True)
        return
    if sys.platform == "win32":
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            WINDOWS_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    WINDOWS_VALUE_NAME,
                    0,
                    winreg.REG_SZ,
                    windows_run_value(program),
                )
            else:
                try:
                    winreg.DeleteValue(key, WINDOWS_VALUE_NAME)
                except OSError:
                    pass
        return
    raise OSError("Launch at login is available on Windows and macOS.")


def _launchctl_load(path: Path) -> None:
    import os
    import subprocess

    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(path)],
        check=False,
        capture_output=True,
    )


def _launchctl_unload(path: Path) -> None:
    import os
    import subprocess

    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(path)],
        check=False,
        capture_output=True,
    )
