"""Shared contracts — models, config, and exceptions used by all layers.

This package defines the API contract between service and web layers.
On microservice split, this becomes a shared library or protobuf definitions.
"""

from src.shared.config import Settings, get_settings
from src.shared.exceptions import (
    AssetNotFoundError,
    BrandComplianceError,
    BriefValidationError,
    ImageGenerationError,
    ImageProcessingError,
    LocalizationError,
    PipelineError,
    TextRenderingError,
)
from src.shared.models import (
    ASPECT_RATIO_CONFIG,
    AspectRatio,
    AssetResult,
    BrandComplianceResult,
    BrandConfig,
    CampaignBrief,
    LegalCheckResult,
    PipelineResult,
    PostMessage,
    Product,
    ProductResult,
)

__all__ = [
    "ASPECT_RATIO_CONFIG",
    "AspectRatio",
    "AssetNotFoundError",
    "AssetResult",
    "BrandComplianceError",
    "BrandComplianceResult",
    "BrandConfig",
    "BriefValidationError",
    "CampaignBrief",
    "ImageGenerationError",
    "ImageProcessingError",
    "LegalCheckResult",
    "LocalizationError",
    "PipelineError",
    "PipelineResult",
    "PostMessage",
    "Product",
    "ProductResult",
    "Settings",
    "TextRenderingError",
    "get_settings",
]
