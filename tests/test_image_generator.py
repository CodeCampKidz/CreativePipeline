"""Tests for GenAI image generation with mocked OpenAI API."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from src.service.integrations.image_generator import ImageGenerator
from src.shared.config import Settings
from src.shared.exceptions import ImageGenerationError
from src.shared.models import AspectRatio, CampaignBrief, Product


def _make_fake_b64_image(width: int = 64, height: int = 64) -> str:
    """Create a base64-encoded PNG image for mocking API responses."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _make_mock_response(b64_data: str | None = None) -> MagicMock:
    """Create a mock OpenAI images.generate response."""
    if b64_data is None:
        b64_data = _make_fake_b64_image()
    image_obj = MagicMock()
    image_obj.b64_json = b64_data
    response = MagicMock()
    response.data = [image_obj]
    return response


def _make_settings(**overrides: Any) -> Settings:
    """Create test settings with sensible defaults."""
    defaults = {
        "openai_api_key": "sk-test-fake-key",
        "image_model": "gpt-image-1",
        "dalle_quality": "standard",
        "image_style": "vivid",
        "max_retries": 2,
        "api_timeout_seconds": 10,
        "fallback_to_placeholder": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def product() -> Product:
    return Product(name="Test Widget", description="A test product widget")


@pytest.fixture
def brief() -> CampaignBrief:
    return CampaignBrief(
        campaign_name="Test Campaign",
        products=[
            Product(name="Test Widget", description="A test widget"),
            Product(name="Test Gadget", description="A test gadget"),
        ],
        target_region="US",
        target_audience="Test audience",
        campaign_message="Test message",
    )


class TestImageGeneratorSuccess:
    """Successful generation scenarios."""

    @pytest.mark.asyncio
    async def test_dalle3_success(
        self, product: Product, brief: CampaignBrief, tmp_path: Path
    ) -> None:
        mock_client = AsyncMock()
        mock_client.images.generate = AsyncMock(return_value=_make_mock_response())
        settings = _make_settings()
        generator = ImageGenerator(mock_client, settings)

        path, source = await generator.generate(product, brief, AspectRatio.SQUARE, tmp_path)
        assert path.exists()
        assert source == "gpt-image-1"
        assert path.suffix == ".png"
        mock_client.images.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_dalle3_fails_dalle2_succeeds(
        self, product: Product, brief: CampaignBrief, tmp_path: Path
    ) -> None:
        mock_client = AsyncMock()
        # DALL-E 3 fails, DALL-E 2 succeeds
        mock_client.images.generate = AsyncMock(
            side_effect=[
                Exception("DALL-E 3 error"),
                Exception("DALL-E 3 retry error"),
                _make_mock_response(),  # DALL-E 2 success
            ]
        )
        settings = _make_settings(max_retries=2)
        generator = ImageGenerator(mock_client, settings)

        path, source = await generator.generate(product, brief, AspectRatio.SQUARE, tmp_path)
        assert path.exists()
        assert source == "dall-e-2"

    @pytest.mark.asyncio
    async def test_all_api_fail_placeholder_generated(
        self, product: Product, brief: CampaignBrief, tmp_path: Path
    ) -> None:
        mock_client = AsyncMock()
        mock_client.images.generate = AsyncMock(side_effect=Exception("API down"))
        settings = _make_settings(max_retries=1)
        generator = ImageGenerator(mock_client, settings, brand_colors=["#FF0000", "#0000FF"])

        path, source = await generator.generate(product, brief, AspectRatio.SQUARE, tmp_path)
        assert path.exists()
        assert source == "placeholder"
        # Verify it's a valid image
        img = Image.open(str(path))
        assert img.width == 1080
        assert img.height == 1080

    @pytest.mark.asyncio
    async def test_skip_genai_produces_placeholder(
        self, product: Product, brief: CampaignBrief, tmp_path: Path
    ) -> None:
        mock_client = AsyncMock()
        settings = _make_settings()
        generator = ImageGenerator(mock_client, settings)

        path, source = await generator.generate(
            product, brief, AspectRatio.PORTRAIT, tmp_path, skip_genai=True
        )
        assert path.exists()
        assert source == "placeholder"
        img = Image.open(str(path))
        assert img.width == 1080
        assert img.height == 1920


class TestImageGeneratorNegative:
    """Negative and edge case scenarios."""

    @pytest.mark.asyncio
    async def test_fallback_disabled_raises(
        self, product: Product, brief: CampaignBrief, tmp_path: Path
    ) -> None:
        mock_client = AsyncMock()
        mock_client.images.generate = AsyncMock(side_effect=Exception("API down"))
        settings = _make_settings(max_retries=1, fallback_to_placeholder=False)
        generator = ImageGenerator(mock_client, settings)

        with pytest.raises(ImageGenerationError, match="All image generation methods failed"):
            await generator.generate(product, brief, AspectRatio.SQUARE, tmp_path)

    @pytest.mark.asyncio
    async def test_null_b64_data_retries(
        self, product: Product, brief: CampaignBrief, tmp_path: Path
    ) -> None:
        null_response = MagicMock()
        null_image = MagicMock()
        null_image.b64_json = None
        null_response.data = [null_image]

        mock_client = AsyncMock()
        mock_client.images.generate = AsyncMock(side_effect=[null_response, _make_mock_response()])
        settings = _make_settings(max_retries=2)
        generator = ImageGenerator(mock_client, settings)

        path, source = await generator.generate(product, brief, AspectRatio.SQUARE, tmp_path)
        assert path.exists()
        assert source == "gpt-image-1"

    @pytest.mark.asyncio
    async def test_placeholder_landscape_dimensions(
        self, product: Product, brief: CampaignBrief, tmp_path: Path
    ) -> None:
        mock_client = AsyncMock()
        mock_client.images.generate = AsyncMock(side_effect=Exception("fail"))
        settings = _make_settings(max_retries=1)
        generator = ImageGenerator(mock_client, settings)

        path, source = await generator.generate(product, brief, AspectRatio.LANDSCAPE, tmp_path)
        img = Image.open(str(path))
        assert img.width == 1920
        assert img.height == 1080
