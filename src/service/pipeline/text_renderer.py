"""Text overlay rendering — campaign message + brand logo compositing on creatives."""

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.service.core.logger import get_logger
from src.shared.exceptions import TextRenderingError

__all__ = ["render_text_overlay"]

logger = get_logger("text_renderer")


def _load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font, falling back to default if unavailable.

    Args:
        font_path: Path to a .ttf font file, or None for default.
        size: Desired font size in pixels.

    Returns:
        A PIL font object.
    """
    if font_path is not None:
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            logger.warning("Font not found at '%s' — using default font", font_path)

    # Try bundled Roboto
    try:
        return ImageFont.truetype("src/assets/fonts/Roboto-Bold.ttf", size)
    except OSError:
        logger.warning("Bundled Roboto font not found — using PIL default")
        return ImageFont.load_default()


def render_text_overlay(
    image: Image.Image,
    message: str,
    logo: Image.Image | None = None,
    font_path: str | None = None,
) -> Image.Image:
    """Render campaign message text and optional logo onto an image.

    Draws a semi-transparent band on the bottom third of the image with
    the campaign message, and composites the brand logo in the top-left corner.

    Args:
        image: Source image to overlay text on (not modified in place).
        message: Campaign message text to render.
        logo: Optional brand logo image (RGBA) to composite.
        font_path: Optional path to a TrueType font file.

    Returns:
        New image with text and logo overlaid.

    Raises:
        TextRenderingError: If rendering encounters an unrecoverable error.
    """
    if not message or not message.strip():
        logger.warning("Empty message — returning image without text overlay")
        return image.copy()

    logger.debug(
        "Rendering text overlay on %dx%d image: '%s'",
        image.width,
        image.height,
        message[:50],
    )

    try:
        # Work on a copy in RGBA mode for transparency support
        result = image.convert("RGBA")
        overlay = Image.new("RGBA", result.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Calculate font size proportional to image width
        font_size = max(image.width // 20, 16)
        font = _load_font(font_path, font_size)

        # Word-wrap the message
        chars_per_line = max(image.width // (font_size // 2 + 1), 10)
        wrapped = textwrap.fill(message, width=chars_per_line)

        # Calculate text bounding box
        bbox = draw.textbbox((0, 0), wrapped, font=font)
        text_h = bbox[3] - bbox[1]
        padding = font_size // 2

        # Draw semi-transparent black band on bottom portion
        band_top = image.height - text_h - (padding * 4)
        band_top = max(band_top, image.height // 2)  # Never cover more than half
        draw.rectangle(
            [(0, band_top), (image.width, image.height)],
            fill=(0, 0, 0, 153),  # 60% opacity black
        )

        # Draw white text centered horizontally in the band
        text_x = padding
        text_y = band_top + padding * 2
        draw.text((text_x, text_y), wrapped, fill=(255, 255, 255, 255), font=font)

        # Composite the overlay onto the result
        result = Image.alpha_composite(result, overlay)

        # Composite logo in top-left corner
        if logo is not None:
            result = _composite_logo(result, logo, padding)

        # Convert back to RGB for PNG saving
        final = result.convert("RGB")
        logger.debug("Text overlay rendering complete")
        return final

    except Exception as exc:
        raise TextRenderingError(
            f"Failed to render text overlay: {exc}",
            detail=f"message='{message[:50]}...'",
        ) from exc


def _composite_logo(
    image: Image.Image,
    logo: Image.Image,
    padding: int,
) -> Image.Image:
    """Composite a brand logo onto the top-left corner of an image.

    Args:
        image: Target RGBA image.
        logo: Logo image (should be RGBA for transparency).
        padding: Pixel padding from the edges.

    Returns:
        Image with logo composited.
    """
    logo_w = image.width // 10
    logo_ratio = logo.height / max(logo.width, 1)
    logo_h = int(logo_w * logo_ratio)
    logo_resized = logo.resize((logo_w, logo_h), Image.LANCZOS)

    if logo_resized.mode != "RGBA":
        logo_resized = logo_resized.convert("RGBA")

    image.paste(logo_resized, (padding, padding), logo_resized)
    logger.debug("Logo composited at (%d, %d), size %dx%d", padding, padding, logo_w, logo_h)
    return image


def load_logo(logo_path: str | Path) -> Image.Image | None:
    """Load a brand logo from disk.

    Args:
        logo_path: Path to logo PNG file.

    Returns:
        PIL Image in RGBA mode, or None if not found.
    """
    path = Path(logo_path)
    if not path.is_file():
        logger.warning("Logo file not found: %s", path)
        return None

    try:
        logo = Image.open(str(path))
        logo = logo.convert("RGBA")
        logger.debug("Loaded logo from %s (%dx%d)", path, logo.width, logo.height)
        return logo
    except Exception as exc:
        logger.warning("Failed to load logo from %s: %s", path, exc)
        return None
