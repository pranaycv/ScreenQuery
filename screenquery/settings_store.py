"""Preferences on disk. The OpenAI API key is intentionally not stored here."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from screenquery.openai_api import DEFAULT_BASE_URL, DEFAULT_MODEL

_LEAKED_KEYS = {"api_key", "openai_api_key", "openAIApiKey", "apikey"}


def config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return root / "ScreenQuery"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ScreenQuery"
    return Path.home() / ".config" / "ScreenQuery"


@dataclass
class Settings:
    save_enabled: bool = True
    llm_enabled: bool = False
    custom_folder: str | None = None
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL

    def to_dict(self) -> dict:
        return {
            "save_enabled": self.save_enabled,
            "llm_enabled": self.llm_enabled,
            "custom_folder": self.custom_folder,
            "base_url": self.base_url,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Settings:
        folder = raw.get("custom_folder")
        if not isinstance(folder, str) or not folder.strip():
            folder = None
        base_url = raw.get("base_url")
        model = raw.get("model")
        return cls(
            save_enabled=bool(raw.get("save_enabled", True)),
            llm_enabled=bool(raw.get("llm_enabled", False)),
            custom_folder=folder,
            base_url=base_url if isinstance(base_url, str) and base_url.strip() else DEFAULT_BASE_URL,
            model=model if isinstance(model, str) and model.strip() else DEFAULT_MODEL,
        )


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (config_dir() / "settings.json")

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return Settings()
        if not isinstance(raw, dict):
            return Settings()
        leaked = any(key in raw for key in _LEAKED_KEYS)
        settings = Settings.from_dict(raw)
        if leaked:
            self.save(settings)
        return settings

    def save(self, settings: Settings) -> None:
        payload = settings.to_dict()
        if _LEAKED_KEYS.intersection(payload):
            raise RuntimeError("Refusing to write an API key into settings.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
