"""Tests for AI post message generation — single-call structured approach."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.service.integrations.message_generator import MessageGenerator
from src.shared.models import CampaignBrief, Product


@pytest.fixture
def product() -> Product:
    return Product(name="Eco Bottle", description="Sustainable reusable water bottle")


@pytest.fixture
def brief() -> CampaignBrief:
    return CampaignBrief(
        campaign_name="Summer Splash 2026",
        products=[
            Product(name="Eco Bottle", description="Sustainable reusable water bottle"),
            Product(name="Sport Cap", description="Lightweight sports cap"),
        ],
        target_region="Latin America",
        target_audience="Health-conscious millennials 25-35",
        campaign_message="Stay Fresh. Stay Green.",
    )


def _mock_structured_response(variants: list[dict[str, object]]) -> MagicMock:
    """Create a mock OpenAI chat response with structured variants JSON."""
    content = json.dumps({"variants": variants})
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


class TestMessageGeneratorPositive:
    """Positive post message generation scenarios."""

    @pytest.mark.asyncio
    async def test_single_call_returns_all_variants(
        self, product: Product, brief: CampaignBrief
    ) -> None:
        mock_response = _mock_structured_response(
            [
                {
                    "language": "en",
                    "aspect_ratio": "1:1",
                    "platform": "Instagram Feed",
                    "text": "Refresh your summer!",
                    "hashtags": ["#EcoBottle", "#GoGreen"],
                },
                {
                    "language": "es",
                    "aspect_ratio": "1:1",
                    "platform": "Instagram Feed",
                    "text": "Refresca tu verano!",
                    "hashtags": ["#EcoBottle", "#VeranoVerde"],
                },
            ]
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        gen = MessageGenerator(mock_client)
        results = await gen.generate_all(product, brief, ["en", "es"], ["1:1"])

        assert len(results) == 2
        assert results[("en", "1:1")].text == "Refresh your summer!"
        assert results[("en", "1:1")].language == "en"
        assert results[("es", "1:1")].text == "Refresca tu verano!"
        assert results[("es", "1:1")].language == "es"
        # Only ONE API call made
        mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_ratios(self, product: Product, brief: CampaignBrief) -> None:
        mock_response = _mock_structured_response(
            [
                {
                    "language": "en",
                    "aspect_ratio": "1:1",
                    "platform": "Instagram",
                    "text": "Feed post!",
                    "hashtags": [],
                },
                {
                    "language": "en",
                    "aspect_ratio": "9:16",
                    "platform": "Stories",
                    "text": "Story post!",
                    "hashtags": [],
                },
                {
                    "language": "en",
                    "aspect_ratio": "16:9",
                    "platform": "YouTube",
                    "text": "Wide post!",
                    "hashtags": [],
                },
            ]
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        gen = MessageGenerator(mock_client)
        results = await gen.generate_all(product, brief, ["en"], ["1:1", "9:16", "16:9"])

        assert len(results) == 3
        assert results[("en", "1:1")].text == "Feed post!"
        assert results[("en", "9:16")].text == "Story post!"
        assert results[("en", "16:9")].text == "Wide post!"

    @pytest.mark.asyncio
    async def test_platform_hints_correct(self, product: Product, brief: CampaignBrief) -> None:
        mock_response = _mock_structured_response(
            [
                {
                    "language": "en",
                    "aspect_ratio": "1:1",
                    "platform": "Instagram Feed",
                    "text": "A",
                    "hashtags": [],
                },
                {
                    "language": "en",
                    "aspect_ratio": "9:16",
                    "platform": "TikTok",
                    "text": "B",
                    "hashtags": [],
                },
                {
                    "language": "en",
                    "aspect_ratio": "16:9",
                    "platform": "YouTube",
                    "text": "C",
                    "hashtags": [],
                },
            ]
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        gen = MessageGenerator(mock_client)
        results = await gen.generate_all(product, brief, ["en"], ["1:1", "9:16", "16:9"])

        assert "Instagram" in results[("en", "1:1")].platform_hint
        assert "TikTok" in results[("en", "9:16")].platform_hint
        assert "YouTube" in results[("en", "16:9")].platform_hint

    @pytest.mark.asyncio
    async def test_languages_stay_distinct(self, product: Product, brief: CampaignBrief) -> None:
        """Key test: English and Spanish variants must be in the correct language."""
        mock_response = _mock_structured_response(
            [
                {
                    "language": "en",
                    "aspect_ratio": "1:1",
                    "platform": "Feed",
                    "text": "Stay fresh this summer!",
                    "hashtags": ["#fresh"],
                },
                {
                    "language": "es",
                    "aspect_ratio": "1:1",
                    "platform": "Feed",
                    "text": "Mantente fresco este verano!",
                    "hashtags": ["#fresco"],
                },
            ]
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        gen = MessageGenerator(mock_client)
        results = await gen.generate_all(product, brief, ["en", "es"], ["1:1"])

        en_msg = results[("en", "1:1")]
        es_msg = results[("es", "1:1")]
        assert en_msg.language == "en"
        assert es_msg.language == "es"
        assert en_msg.text != es_msg.text


class TestMessageGeneratorNegative:
    """Negative and fallback scenarios."""

    @pytest.mark.asyncio
    async def test_api_failure_falls_back(self, product: Product, brief: CampaignBrief) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API down"))
        gen = MessageGenerator(mock_client)

        results = await gen.generate_all(product, brief, ["en", "es"], ["1:1"])
        assert len(results) == 2
        assert results[("en", "1:1")].text == brief.campaign_message
        assert results[("es", "1:1")].text == brief.campaign_message

    @pytest.mark.asyncio
    async def test_missing_variants_filled_with_fallback(
        self, product: Product, brief: CampaignBrief
    ) -> None:
        """LLM returns fewer variants than requested — missing ones get fallback."""
        mock_response = _mock_structured_response(
            [
                {
                    "language": "en",
                    "aspect_ratio": "1:1",
                    "platform": "Feed",
                    "text": "English!",
                    "hashtags": [],
                },
                # Missing: es / 1:1
            ]
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        gen = MessageGenerator(mock_client)
        results = await gen.generate_all(product, brief, ["en", "es"], ["1:1"])

        assert results[("en", "1:1")].text == "English!"
        assert results[("es", "1:1")].text == brief.campaign_message  # Fallback

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back(self, product: Product, brief: CampaignBrief) -> None:
        choice = MagicMock()
        choice.message.content = "not valid json"
        response = MagicMock()
        response.choices = [choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=response)
        gen = MessageGenerator(mock_client)

        results = await gen.generate_all(product, brief, ["en"], ["1:1"])
        assert results[("en", "1:1")].text == brief.campaign_message
