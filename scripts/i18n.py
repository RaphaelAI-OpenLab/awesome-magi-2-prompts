"""Language routes and UI copy helpers, standard library only."""

from __future__ import annotations

LANGUAGE_NAMES = {
    "en": "English",
    "zh-CN": "简体中文",
}
LANGUAGES = tuple(LANGUAGE_NAMES)
DETAIL_LANGUAGES = ("en", "zh-CN")


def filename(language: str) -> str:
    """Return the root README filename for a supported locale."""
    if language not in LANGUAGE_NAMES:
        raise ValueError(f"Unsupported locale: {language}")
    return "README.md" if language == "en" else f"README.{language}.md"


def ui(english: str, chinese: str | None = None, language: str = "en") -> str:
    """Select English or Simplified Chinese copy cleanly."""
    if language == "en":
        return english
    if language == "zh-CN":
        return chinese if chinese is not None else english
    raise ValueError(f"Unsupported locale: {language}")
