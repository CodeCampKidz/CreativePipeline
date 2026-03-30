"""Tests for legal content checking — prohibited words scanning."""

from __future__ import annotations

from src.service.compliance.legal_checker import check_legal_content


class TestLegalCheckerPositive:
    """Positive legal check scenarios."""

    def test_clean_message_passes(self) -> None:
        result = check_legal_content(
            "Stay Fresh. Stay Green. Summer Splash 2026",
            ["guaranteed", "miracle", "cure"],
        )
        assert result.passed is True
        assert len(result.flagged_terms) == 0

    def test_empty_prohibited_list_passes(self) -> None:
        result = check_legal_content("Any message at all", [])
        assert result.passed is True
        assert "No prohibited words configured" in result.message

    def test_word_boundary_freedom_not_flagged(self) -> None:
        result = check_legal_content(
            "Experience the freedom of choice",
            ["free"],
        )
        assert result.passed is True
        assert len(result.flagged_terms) == 0

    def test_word_boundary_cured_not_flagged(self) -> None:
        result = check_legal_content(
            "Our specially cured leather",
            ["cure"],
        )
        assert result.passed is True

    def test_case_insensitive_no_false_positive(self) -> None:
        result = check_legal_content(
            "A truly remarkable product",
            ["guaranteed", "miracle"],
        )
        assert result.passed is True


class TestLegalCheckerNegative:
    """Negative legal check scenarios — terms that should be flagged."""

    def test_single_prohibited_word_flagged(self) -> None:
        result = check_legal_content(
            "Get guaranteed results today!",
            ["guaranteed"],
        )
        assert result.passed is False
        assert len(result.flagged_terms) == 1
        assert result.flagged_terms[0]["term"] == "guaranteed"

    def test_multiple_prohibited_words_all_flagged(self) -> None:
        result = check_legal_content(
            "This miracle cure is guaranteed to work!",
            ["guaranteed", "miracle", "cure"],
        )
        assert result.passed is False
        assert len(result.flagged_terms) == 3
        flagged_terms = {f["term"] for f in result.flagged_terms}
        assert flagged_terms == {"guaranteed", "miracle", "cure"}

    def test_case_insensitive_matching(self) -> None:
        result = check_legal_content(
            "GUARANTEED Results",
            ["guaranteed"],
        )
        assert result.passed is False
        assert result.flagged_terms[0]["matched"] == "GUARANTEED"

    def test_phrase_matching(self) -> None:
        result = check_legal_content(
            "This product has no side effects whatsoever",
            ["no side effects"],
        )
        assert result.passed is False
        assert result.flagged_terms[0]["term"] == "no side effects"

    def test_context_included_in_flag(self) -> None:
        result = check_legal_content(
            "Buy now for guaranteed satisfaction",
            ["guaranteed"],
        )
        assert result.passed is False
        assert "context" in result.flagged_terms[0]
        assert "guaranteed" in result.flagged_terms[0]["context"]

    def test_multiple_occurrences_of_same_word(self) -> None:
        result = check_legal_content(
            "Guaranteed quality, guaranteed delivery",
            ["guaranteed"],
        )
        assert result.passed is False
        assert len(result.flagged_terms) == 2
