"""Pydantic data models for campaign briefs, brand configuration, and pipeline results."""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from src.shared.exceptions import BriefValidationError

__all__ = [
    "ASPECT_RATIO_CONFIG",
    "AspectRatio",
    "AssetResult",
    "BrandComplianceResult",
    "BrandConfig",
    "CampaignBrief",
    "LegalCheckResult",
    "PipelineResult",
    "Product",
    "ProductResult",
]


class AspectRatio(str, Enum):
    """Supported social media aspect ratios."""

    SQUARE = "1:1"
    PORTRAIT = "9:16"
    LANDSCAPE = "16:9"


# Maps AspectRatio to DALL-E 3 native sizes and final social-media pixel dimensions.
ASPECT_RATIO_CONFIG: dict[AspectRatio, dict[str, Any]] = {
    AspectRatio.SQUARE: {
        "dalle_size": "1024x1024",
        "pixels": (1080, 1080),
        "folder": "1x1",
    },
    AspectRatio.PORTRAIT: {
        "dalle_size": "1024x1792",
        "pixels": (1080, 1920),
        "folder": "9x16",
    },
    AspectRatio.LANDSCAPE: {
        "dalle_size": "1792x1024",
        "pixels": (1920, 1080),
        "folder": "16x9",
    },
}


class Product(BaseModel):
    """A product within a campaign brief."""

    name: str = Field(..., min_length=1, description="Product display name")
    description: str = Field(
        ..., min_length=1, description="Short product description used in image generation prompts"
    )
    asset_folder: str | None = Field(
        default=None, description="Path to folder containing existing hero images"
    )


class CampaignBrief(BaseModel):
    """Campaign brief defining products, audience, and creative parameters."""

    campaign_name: str = Field(..., min_length=1, description="Unique campaign identifier")
    products: list[Product] = Field(
        ..., min_length=2, description="Products to generate creatives for (minimum 2)"
    )
    target_region: str = Field(..., min_length=1, description="Target geographic region or market")
    target_audience: str = Field(
        ..., min_length=1, description="Target audience demographic description"
    )
    campaign_message: str = Field(
        ..., min_length=1, description="Primary campaign message overlaid on creatives"
    )
    languages: list[str] = Field(
        default=["en"], description="ISO 639-1 language codes for localization"
    )
    aspect_ratios: list[AspectRatio] = Field(
        default=[AspectRatio.SQUARE, AspectRatio.PORTRAIT, AspectRatio.LANDSCAPE],
        description="Target aspect ratios for creative output",
    )

    @field_validator("products")
    @classmethod
    def validate_min_products(cls, v: list[Product]) -> list[Product]:
        """Ensure at least two products are specified."""
        if len(v) < 2:
            raise ValueError("Campaign must include at least 2 products")
        return v

    @field_validator("languages")
    @classmethod
    def validate_languages(cls, v: list[str]) -> list[str]:
        """Ensure at least one language is specified and codes are valid format."""
        if not v:
            raise ValueError("At least one language code is required")
        for lang in v:
            if len(lang) != 2 or not lang.isalpha():
                raise ValueError(f"Invalid ISO 639-1 language code: '{lang}'")
        return [lang.lower() for lang in v]

    @classmethod
    def from_file(cls, path: Path) -> CampaignBrief:
        """Load and validate a campaign brief from a YAML or JSON file.

        Args:
            path: Path to YAML or JSON brief file.

        Returns:
            Validated CampaignBrief instance.

        Raises:
            BriefValidationError: If file cannot be read or fails validation.
        """
        if not path.exists():
            raise BriefValidationError(f"Brief file not found: {path}", detail=str(path))

        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise BriefValidationError(f"Cannot read brief file: {exc}", detail=str(path)) from exc

        suffix = path.suffix.lower()
        try:
            if suffix in {".yaml", ".yml"}:
                data = yaml.safe_load(raw_text)
            elif suffix == ".json":
                data = json.loads(raw_text)
            else:
                raise BriefValidationError(
                    f"Unsupported brief format: {suffix}. Use .yaml, .yml, or .json",
                    detail=suffix,
                )
        except (yaml.YAMLError, ValueError) as exc:
            raise BriefValidationError(
                f"Failed to parse brief file: {exc}", detail=str(path)
            ) from exc

        if not isinstance(data, dict):
            raise BriefValidationError(
                "Brief file must contain a YAML/JSON object, not a list or scalar",
                detail=str(type(data)),
            )

        try:
            return cls.model_validate(data)
        except Exception as exc:
            raise BriefValidationError(f"Brief validation failed: {exc}", detail=str(exc)) from exc


class BrandConfig(BaseModel):
    """Brand guidelines configuration."""

    brand_name: str = Field(..., min_length=1, description="Brand display name")
    primary_colors: list[str] = Field(
        ..., description="Hex color codes, e.g. ['#00A86B', '#1A1A2E']"
    )
    logo_path: str = Field(..., description="Path to brand logo PNG file")
    prohibited_words: list[str] = Field(
        default_factory=list, description="Words prohibited in campaign content"
    )
    font_path: str | None = Field(default=None, description="Path to custom TrueType font file")

    @field_validator("primary_colors")
    @classmethod
    def validate_hex_colors(cls, v: list[str]) -> list[str]:
        """Validate that all colors are valid hex codes."""
        for color in v:
            if not re.match(r"^#[0-9A-Fa-f]{6}$", color):
                raise ValueError(f"Invalid hex color code: '{color}'")
        return v

    @classmethod
    def from_file(cls, path: Path) -> BrandConfig:
        """Load brand configuration from a YAML file.

        Args:
            path: Path to brand config YAML file.

        Returns:
            Validated BrandConfig instance.

        Raises:
            BriefValidationError: If file cannot be read or fails validation.
        """
        if not path.exists():
            raise BriefValidationError(f"Brand config file not found: {path}", detail=str(path))
        try:
            raw = path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
            return cls.model_validate(data)
        except Exception as exc:
            raise BriefValidationError(
                f"Brand config validation failed: {exc}", detail=str(exc)
            ) from exc


# --- Pipeline result models ---


class BrandComplianceResult(BaseModel):
    """Result of a brand compliance check on a single creative."""

    status: str = Field(..., description="'pass', 'warn', or 'fail'")
    logo_present: bool = Field(..., description="Whether the brand logo was composited")
    color_match_percentage: float = Field(
        ..., description="Percentage of dominant colors matching brand palette"
    )
    details: list[str] = Field(default_factory=list, description="Compliance details/warnings")


class LegalCheckResult(BaseModel):
    """Result of a legal content check on campaign message text."""

    passed: bool = Field(..., description="True if no prohibited content found")
    flagged_terms: list[dict[str, str]] = Field(
        default_factory=list, description="List of flagged terms with context"
    )
    message: str = Field(..., description="Summary of legal check result")


class PostMessage(BaseModel):
    """AI-generated social media post message paired with a creative."""

    text: str = Field(..., description="The post message text")
    hashtags: list[str] = Field(default_factory=list, description="Suggested hashtags")
    platform_hint: str = Field(
        default="general", description="Platform this message is optimized for"
    )
    language: str = Field(default="en", description="ISO 639-1 language code")


class AssetResult(BaseModel):
    """Result for a single generated or reused creative asset."""

    product_name: str
    aspect_ratio: str
    language: str
    output_path: str
    source: str = Field(
        ..., description="'existing', model name (e.g. 'gpt-image-1'), or 'placeholder'"
    )
    generation_time_seconds: float = 0.0
    post_message: PostMessage | None = Field(
        default=None, description="AI-generated social media post message"
    )


class ProductResult(BaseModel):
    """Aggregated result for a single product."""

    product_name: str
    assets: list[AssetResult] = Field(default_factory=list)
    brand_compliance: BrandComplianceResult | None = None
    errors: list[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    """Overall pipeline execution result."""

    campaign_name: str
    version: int = Field(default=1, description="Output version number")
    total_assets_generated: int = 0
    total_assets_reused: int = 0
    total_assets_placeholder: int = 0
    products: list[ProductResult] = Field(default_factory=list)
    legal_check: LegalCheckResult | None = None
    total_time_seconds: float = 0.0
    errors: list[str] = Field(default_factory=list)
