"""Custom exception hierarchy for the Creative Automation Pipeline."""

__all__ = [
    "AssetNotFoundError",
    "BrandComplianceError",
    "BriefValidationError",
    "ImageGenerationError",
    "ImageProcessingError",
    "LocalizationError",
    "PipelineError",
    "TextRenderingError",
]


class PipelineError(Exception):
    """Base exception for all pipeline errors."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        self.detail = detail
        super().__init__(message)


class BriefValidationError(PipelineError):
    """Raised when a campaign brief fails validation."""


class AssetNotFoundError(PipelineError):
    """Raised when a required asset cannot be located or resolved."""


class ImageGenerationError(PipelineError):
    """Raised when GenAI image generation fails after all retries and fallbacks."""


class ImageProcessingError(PipelineError):
    """Raised when image resize, crop, or transformation fails."""


class TextRenderingError(PipelineError):
    """Raised when text overlay or logo compositing fails."""


class BrandComplianceError(PipelineError):
    """Raised when brand compliance checking encounters an unrecoverable error."""


class LocalizationError(PipelineError):
    """Raised when translation or localization fails."""
