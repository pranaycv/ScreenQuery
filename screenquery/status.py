"""What the floating status window displays after a capture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Status:
    banner: str | None = None
    banner_is_error: bool = False
    save_display: str | None = None
    save_full: str | None = None
    save_error: str | None = None
    llm_working: bool = False
    answer: str | None = None
    llm_error: str | None = None

    @property
    def has_answer(self) -> bool:
        return bool(self.answer)

    @property
    def has_error(self) -> bool:
        return bool(self.banner_is_error or self.save_error or self.llm_error)


def dismiss_seconds(status: Status) -> float | None:
    """How long the overlay stays up. None while OpenAI is still working."""
    if status.llm_working:
        return None
    if status.has_answer:
        return 20
    if status.has_error:
        return 12
    return 8
