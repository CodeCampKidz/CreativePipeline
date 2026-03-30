"""Image processing — resize and smart center-crop to target aspect ratios."""

from __future__ import annotations

from PIL import Image

from src.service.core.logger import get_logger
from src.shared.exceptions import ImageProcessingError
from src.shared.models import ASPECT_RATIO_CONFIG, AspectRatio

__all__ = ["resize_and_crop"]

logger = get_logger("image_processor")


def resize_and_crop(image: Image.Image, aspect_ratio: AspectRatio) -> Image.Image:
    """Resize and smart-crop an image to match the target aspect ratio dimensions.

    Strategy: resize so the shortest dimension fills the target, then center-crop
    the longer dimension to achieve exact target pixel dimensions.

    Args:
        image: Source PIL Image to process.
        aspect_ratio: Target AspectRatio enum value.

    Returns:
        New PIL Image at the exact target dimensions.

    Raises:
        ImageProcessingError: If the source image has invalid dimensions.
    """
    config = ASPECT_RATIO_CONFIG[aspect_ratio]
    target_w, target_h = config["pixels"]

    if image.width <= 0 or image.height <= 0:
        raise ImageProcessingError(
            f"Invalid source image dimensions: {image.width}x{image.height}",
            detail=f"aspect_ratio={aspect_ratio.value}",
        )

    logger.debug(
        "Resizing image %dx%d → %dx%d (%s)",
        image.width,
        image.height,
        target_w,
        target_h,
        aspect_ratio.value,
    )

    # Ensure RGB mode for consistency
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")

    img_ratio = image.width / image.height
    target_ratio = target_w / target_h

    if img_ratio > target_ratio:
        # Source is wider: fit height, crop width
        new_h = target_h
        new_w = int(target_h * img_ratio)
    else:
        # Source is taller (or same): fit width, crop height
        new_w = target_w
        new_h = int(target_w / img_ratio)

    # Resize with high-quality resampling
    resized = image.resize((new_w, new_h), Image.LANCZOS)

    # Center-crop to exact target dimensions
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    cropped = resized.crop((left, top, left + target_w, top + target_h))

    logger.debug(
        "Resize complete: %dx%d → %dx%d (intermediate %dx%d)",
        image.width,
        image.height,
        cropped.width,
        cropped.height,
        new_w,
        new_h,
    )

    return cropped
