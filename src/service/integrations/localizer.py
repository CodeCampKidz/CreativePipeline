"""Localization — translate campaign messages to target languages."""

from __future__ import annotations

import asyncio

from deep_translator import GoogleTranslator

from src.service.core.logger import get_logger
from src.shared.exceptions import LocalizationError

__all__ = ["translate_text"]

logger = get_logger("localizer")


async def translate_text(text: str, target_language: str) -> str:
    """Translate text to a target language using Google Translate (free tier).

    Args:
        text: Source text in English.
        target_language: ISO 639-1 target language code (e.g., 'es', 'fr', 'de').

    Returns:
        Translated text string.

    Raises:
        LocalizationError: If translation fails.
    """
    if target_language == "en":
        return text

    logger.debug("Translating to '%s': '%s'", target_language, text[:50])

    try:
        translated = await asyncio.to_thread(_translate_sync, text, target_language)
        logger.info("Translated to '%s': '%s' → '%s'", target_language, text[:30], translated[:30])
        return translated
    except Exception as exc:
        raise LocalizationError(
            f"Translation to '{target_language}' failed: {exc}",
            detail=f"source='{text[:50]}'",
        ) from exc


def _translate_sync(text: str, target_language: str) -> str:
    """Synchronous translation wrapper.

    Args:
        text: Source text.
        target_language: Target language code.

    Returns:
        Translated text.
    """
    translator = GoogleTranslator(source="en", target=target_language)
    result: str = translator.translate(text)
    return result
