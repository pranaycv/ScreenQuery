"""System keychain for the OpenAI API key.

macOS uses Keychain, Windows uses Credential Manager, via the keyring package.
The key is never written to settings.json.
"""

from __future__ import annotations

SERVICE = "com.screenquery.ScreenQuery"
ACCOUNT = "openai-api-key"


class MemoryKeyring:
    """In-memory stand-in used by tests."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, account: str) -> str | None:
        return self._items.get((service, account))

    def set_password(self, service: str, account: str, password: str) -> None:
        self._items[(service, account)] = password

    def delete_password(self, service: str, account: str) -> None:
        self._items.pop((service, account), None)


class Keystore:
    def __init__(self, backend=None) -> None:
        self._backend = backend

    def load(self) -> str | None:
        value = self._ring().get_password(SERVICE, ACCOUNT)
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def save(self, secret: str) -> None:
        trimmed = secret.strip()
        if not trimmed:
            self.delete()
            return
        self._ring().set_password(SERVICE, ACCOUNT, trimmed)

    def delete(self) -> None:
        ring = self._ring()
        try:
            ring.delete_password(SERVICE, ACCOUNT)
        except Exception as exc:  # keyring raises if the item is already gone
            if exc.__class__.__name__ == "PasswordDeleteError":
                return
            if "not found" in str(exc).lower():
                return
            raise

    def _ring(self):
        if self._backend is not None:
            return self._backend
        import keyring

        return keyring
