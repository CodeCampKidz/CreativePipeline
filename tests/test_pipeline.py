"""Integration tests for the pipeline orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.service import Pipeline
from src.shared.config import Settings
from src.shared.models import CampaignBrief


def _make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    """Create test settings pointing to temp directories."""
    defaults = {
        "openai_api_key": "sk-test-fake",
        "output_dir": str(tmp_path / "output"),
        "input_assets_dir": str(tmp_path / "input_assets"),
        "brand_config_path": str(tmp_path / "brand_config.yaml"),
        "log_level": "WARNING",
        "max_retries": 1,
        "api_timeout_seconds": 5,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestPipelineIntegration:
    """Integration tests with mocked GenAI."""

    @pytest.mark.asyncio
    async def test_dry_run_produces_no_output(
        self,
        sample_brief: CampaignBrief,
        tmp_path: Path,
    ) -> None:
        settings = _make_settings(tmp_path)
        pipeline = Pipeline(settings, sample_brief)
        result = await pipeline.run(dry_run=True)

        assert result.campaign_name == sample_brief.campaign_name
        assert result.total_assets_generated == 0
        assert result.total_assets_reused == 0

    @pytest.mark.asyncio
    async def test_skip_genai_produces_placeholders(
        self,
        sample_brief: CampaignBrief,
        tmp_path: Path,
    ) -> None:
        settings = _make_settings(tmp_path)
        # Create input_assets dirs so asset manager works
        for product in sample_brief.products:
            (tmp_path / "input_assets" / product.name.lower().replace(" ", "_")).mkdir(
                parents=True, exist_ok=True
            )

        pipeline = Pipeline(settings, sample_brief)
        result = await pipeline.run(skip_genai=True)

        assert result.total_assets_placeholder > 0
        assert result.total_time_seconds > 0
        # Should have assets for each product * ratio * language
        total_expected = (
            len(sample_brief.products)
            * len(sample_brief.aspect_ratios)
            * len(sample_brief.languages)
        )
        total_actual = sum(len(pr.assets) for pr in result.products)
        assert total_actual == total_expected

    @pytest.mark.asyncio
    async def test_pipeline_result_structure(
        self,
        sample_brief: CampaignBrief,
        tmp_path: Path,
    ) -> None:
        settings = _make_settings(tmp_path)
        pipeline = Pipeline(settings, sample_brief)
        result = await pipeline.run(skip_genai=True)

        assert result.campaign_name == "Test Campaign 2026"
        assert len(result.products) == 2
        for pr in result.products:
            assert pr.product_name in ["Eco Bottle", "Sport Cap"]
            for asset in pr.assets:
                assert asset.aspect_ratio in ["1:1", "9:16", "16:9"]
                assert asset.language in ["en", "es"]
                assert asset.source == "placeholder"
                assert Path(asset.output_path).name.startswith("creative_")

    @pytest.mark.asyncio
    async def test_output_folders_created(
        self,
        sample_brief: CampaignBrief,
        tmp_path: Path,
    ) -> None:
        settings = _make_settings(tmp_path)
        pipeline = Pipeline(settings, sample_brief)
        result = await pipeline.run(skip_genai=True)

        output_base = tmp_path / "output" / "test-campaign-2026"
        assert output_base.exists()
        # Check folder structure
        for pr in result.products:
            for asset in pr.assets:
                assert Path(asset.output_path).exists()
