"""Legal content checking — flag prohibited words in campaign text."""

from __future__ import annotations

import re

from src.service.core.logger import get_logger
from src.shared.models import LegalCheckResult

__all__ = ["check_legal_content"]

logger = get_logger("legal_checker")


def check_legal_content(
    message: str,
    prohibited_words: list[str],
) -> LegalCheckResult:
    """Scan campaign message text for prohibited words or phrases.

    Uses word boundary matching to avoid false positives (e.g., "freedom"
    does not match "free"). Matching is case-insensitive.

    Args:
        message: Campaign message text to check.
        prohibited_words: List of prohibited words or phrases.

    Returns:
        LegalCheckResult with pass/fail status and any flagged terms.
    """
    logger.debug("Running legal check on message: '%s'", message[:100])
    logger.debug("Checking against %d prohibited terms", len(prohibited_words))

    if not prohibited_words:
        logger.info("No prohibited words configured — legal check passed")
        return LegalCheckResult(
            passed=True,
            flagged_terms=[],
            message="No prohibited words configured",
        )

    flagged: list[dict[str, str]] = []

    for term in prohibited_words:
        # Word boundaries for single words, literal match for phrases
        pattern = re.escape(term) if " " in term else rf"\b{re.escape(term)}\b"

        matches = list(re.finditer(pattern, message, re.IGNORECASE))
        for match in matches:
            start = max(0, match.start() - 20)
            end = min(len(message), match.end() + 20)
            context = message[start:end]
            flagged.append(
                {
                    "term": term,
                    "matched": match.group(),
                    "context": f"...{context}...",
                }
            )
            logger.warning("Prohibited term found: '%s' in context: '...%s...'", term, context)

    passed = len(flagged) == 0
    summary = (
        "Legal check passed — no prohibited content found"
        if passed
        else f"Legal check flagged {len(flagged)} term(s): {', '.join(f['term'] for f in flagged)}"
    )

    logger.info("Legal check result: %s", "PASSED" if passed else "FLAGGED")
    return LegalCheckResult(passed=passed, flagged_terms=flagged, message=summary)
