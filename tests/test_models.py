"""Tests for Pydantic data models — campaign brief and brand config validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.shared.exceptions import BriefValidationError
from src.shared.models import (
    AspectRatio,
    BrandConfig,
    CampaignBrief,
    Product,
)

# ── Positive Tests ──────────────────────────────────────────────────────────


class TestProductValid:
    """Valid Product model scenarios."""

    def test_minimal_product(self) -> None:
        product = Product(name="Widget", description="A widget")
        assert product.name == "Widget"
        assert product.asset_folder is None

    def test_product_with_asset_folder(self) -> None:
        product = Product(name="Widget", description="A widget", asset_folder="assets/widget")
        assert product.asset_folder == "assets/widget"


class TestCampaignBriefValid:
    """Valid CampaignBrief model scenarios."""

    def test_valid_brief_two_products(self, sample_brief_dict: dict[str, Any]) -> None:
        brief = CampaignBrief.model_validate(sample_brief_dict)
        assert brief.campaign_name == "Test Campaign 2026"
        assert len(brief.products) == 2
        assert brief.target_region == "Latin America"

    def test_valid_brief_many_products(self, sample_brief_dict: dict[str, Any]) -> None:
        sample_brief_dict["products"].append({"name": "Third", "description": "Third product"})
        brief = CampaignBrief.model_validate(sample_brief_dict)
        assert len(brief.products) == 3

    def test_default_languages(self) -> None:
        data = {
            "campaign_name": "Test",
            "products": [
                {"name": "A", "description": "a"},
                {"name": "B", "description": "b"},
            ],
            "target_region": "US",
            "target_audience": "All",
            "campaign_message": "Hello",
        }
        brief = CampaignBrief.model_validate(data)
        assert brief.languages == ["en"]

    def test_default_aspect_ratios(self) -> None:
        data = {
            "campaign_name": "Test",
            "products": [
                {"name": "A", "description": "a"},
                {"name": "B", "description": "b"},
            ],
            "target_region": "US",
            "target_audience": "All",
            "campaign_message": "Hello",
        }
        brief = CampaignBrief.model_validate(data)
        assert len(brief.aspect_ratios) == 3
        assert AspectRatio.SQUARE in brief.aspect_ratios

    def test_language_codes_lowercased(self) -> None:
        data = {
            "campaign_name": "Test",
            "products": [
                {"name": "A", "description": "a"},
                {"name": "B", "description": "b"},
            ],
            "target_region": "US",
            "target_audience": "All",
            "campaign_message": "Hello",
            "languages": ["EN", "Es"],
        }
        brief = CampaignBrief.model_validate(data)
        assert brief.languages == ["en", "es"]

    def test_from_yaml_file(self, sample_brief_yaml: Path) -> None:
        brief = CampaignBrief.from_file(sample_brief_yaml)
        assert brief.campaign_name == "Test Campaign 2026"
        assert len(brief.products) == 2

    def test_from_json_file(self, sample_brief_json: Path) -> None:
        brief = CampaignBrief.from_file(sample_brief_json)
        assert brief.campaign_name == "Test Campaign 2026"


# ── Negative Tests ──────────────────────────────────────────────────────────


class TestProductInvalid:
    """Invalid Product model scenarios."""

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            Product(name="", description="desc")

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            Product(name="Widget", description="")


class TestCampaignBriefInvalid:
    """Invalid CampaignBrief model scenarios."""

    def test_one_product_rejected(self, invalid_brief_dict: dict[str, Any]) -> None:
        with pytest.raises(ValidationError, match="at least 2"):
            CampaignBrief.model_validate(invalid_brief_dict)

    def test_zero_products_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CampaignBrief.model_validate(
                {
                    "campaign_name": "Test",
                    "products": [],
                    "target_region": "US",
                    "target_audience": "All",
                    "campaign_message": "Hello",
                }
            )

    def test_missing_campaign_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="campaign_name"):
            CampaignBrief.model_validate(
                {
                    "products": [
                        {"name": "A", "description": "a"},
                        {"name": "B", "description": "b"},
                    ],
                    "target_region": "US",
                    "target_audience": "All",
                    "campaign_message": "Hello",
                }
            )

    def test_empty_campaign_message_rejected(self) -> None:
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            CampaignBrief.model_validate(
                {
                    "campaign_name": "Test",
                    "products": [
                        {"name": "A", "description": "a"},
                        {"name": "B", "description": "b"},
                    ],
                    "target_region": "US",
                    "target_audience": "All",
                    "campaign_message": "",
                }
            )

    def test_invalid_aspect_ratio_rejected(self) -> None:
        with pytest.raises(ValidationError, match="aspect_ratios"):
            CampaignBrief.model_validate(
                {
                    "campaign_name": "Test",
                    "products": [
                        {"name": "A", "description": "a"},
                        {"name": "B", "description": "b"},
                    ],
                    "target_region": "US",
                    "target_audience": "All",
                    "campaign_message": "Hello",
                    "aspect_ratios": ["4:3"],
                }
            )

    def test_invalid_language_code_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid ISO 639-1"):
            CampaignBrief.model_validate(
                {
                    "campaign_name": "Test",
                    "products": [
                        {"name": "A", "description": "a"},
                        {"name": "B", "description": "b"},
                    ],
                    "target_region": "US",
                    "target_audience": "All",
                    "campaign_message": "Hello",
                    "languages": ["english"],
                }
            )

    def test_empty_languages_list_rejected(self) -> None:
        with pytest.raises(ValidationError, match="At least one language"):
            CampaignBrief.model_validate(
                {
                    "campaign_name": "Test",
                    "products": [
                        {"name": "A", "description": "a"},
                        {"name": "B", "description": "b"},
                    ],
                    "target_region": "US",
                    "target_audience": "All",
                    "campaign_message": "Hello",
                    "languages": [],
                }
            )

    def test_from_file_nonexistent_raises(self, tmp_path: Path) -> None:
        with pytest.raises(BriefValidationError, match="not found"):
            CampaignBrief.from_file(tmp_path / "nonexistent.yaml")

    def test_from_file_unsupported_format_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "brief.xml"
        bad.write_text("<xml/>")
        with pytest.raises(BriefValidationError, match="Unsupported brief format"):
            CampaignBrief.from_file(bad)

    def test_from_file_invalid_yaml_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "brief.yaml"
        bad.write_text("{{{{invalid yaml")
        with pytest.raises(BriefValidationError, match="Failed to parse"):
            CampaignBrief.from_file(bad)

    def test_from_file_yaml_list_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "brief.yaml"
        bad.write_text("- item1\n- item2\n")
        with pytest.raises(BriefValidationError, match="must contain a YAML/JSON object"):
            CampaignBrief.from_file(bad)


# ── Brand Config Tests ──────────────────────────────────────────────────────


class TestBrandConfigValid:
    """Valid BrandConfig scenarios."""

    def test_valid_config(self) -> None:
        config = BrandConfig(
            brand_name="FreshCo",
            primary_colors=["#00A86B", "#1A1A2E"],
            logo_path="logo.png",
        )
        assert config.brand_name == "FreshCo"
        assert len(config.primary_colors) == 2

    def test_config_with_optional_fields(self) -> None:
        config = BrandConfig(
            brand_name="FreshCo",
            primary_colors=["#FFFFFF"],
            logo_path="logo.png",
            prohibited_words=["guaranteed"],
            font_path="fonts/Roboto.ttf",
        )
        assert config.prohibited_words == ["guaranteed"]
        assert config.font_path == "fonts/Roboto.ttf"


class TestBrandConfigInvalid:
    """Invalid BrandConfig scenarios."""

    def test_invalid_hex_color_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid hex color"):
            BrandConfig(
                brand_name="Test",
                primary_colors=["not-a-color"],
                logo_path="logo.png",
            )

    def test_short_hex_color_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid hex color"):
            BrandConfig(
                brand_name="Test",
                primary_colors=["#FFF"],
                logo_path="logo.png",
            )

    def test_empty_brand_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            BrandConfig(
                brand_name="",
                primary_colors=["#FFFFFF"],
                logo_path="logo.png",
            )
