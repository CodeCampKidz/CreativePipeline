"""GenAI image generation with three-tier fallback: DALL-E 3 → DALL-E 2 → placeholder."""

from __future__ import annotations

import asyncio
import base64
import io
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

from src.service.core.colors import hex_to_rgb
from src.service.core.logger import get_logger
from src.shared.exceptions import ImageGenerationError
from src.shared.models import ASPECT_RATIO_CONFIG, AspectRatio

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from src.shared.config import Settings
    from src.shared.models import CampaignBrief, Product

__all__ = ["ImageGenerator"]

logger = get_logger("image_generator")


def _build_prompt(
    product: Product,
    brief: CampaignBrief,
    direction_fragment: str | None = None,
) -> str:
    """Build an image generation prompt from product, campaign, and creative direction.

    When a CreativeDirection fragment is provided (from the AI Creative Director),
    it is used for contextually appropriate style guidance. Without it, a minimal
    prompt is used as fallback.

    Args:
        product: The product to generate an image for.
        brief: The campaign brief with audience and region context.
        direction_fragment: Pre-formatted style/composition/lighting fragment
            from CreativeDirection.to_image_prompt_fragment().

    Returns:
        A descriptive prompt string for the GenAI model.
    """
    # Product-hero framing is always enforced regardless of creative direction
    product_focus = (
        f"IMPORTANT: The {product.name} must be the HERO of this image — "
        f"the largest, most prominent element, occupying at least 60% of the frame. "
        f"The product must be sharply focused, beautifully lit, and positioned front and center. "
        f"This is a product advertisement designed to make people want to buy it. "
    )

    no_text = (
        "CRITICAL RULE: The image must contain ZERO text, ZERO words, ZERO letters, "
        "ZERO numbers, ZERO logos, ZERO watermarks, ZERO captions, ZERO slogans, "
        "ZERO hashtags, and ZERO typographic elements of any kind. "
        "This is a pure photographic image only. Any form of writing in the image is strictly forbidden. "
    )

    base = (
        f"{no_text}"
        f"Professional product-focused photographic image of {product.name}. "
        f"Product description: {product.description}. "
        f"The visual mood should evoke freshness, sustainability, and summer energy. "
        f"Target market: {brief.target_region}. "
        f"{product_focus}"
    )

    if direction_fragment:
        style = direction_fragment
    else:
        style = (
            "Style: premium product photography, clean background, "
            "the product is hero-lit and dominates the frame."
        )

    prompt = f"{base}{style} REMINDER: Absolutely no text, words, or letters anywhere in the image."
    logger.debug("Built prompt (%d chars): %s", len(prompt), prompt[:150])
    return prompt


class ImageGenerator:
    """Generates product images via OpenAI DALL-E with graceful fallback.

    Fallback chain:
        1. DALL-E 3 (primary, highest quality)
        2. DALL-E 2 (fallback, faster and cheaper)
        3. Local placeholder (gradient image with product name)
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        settings: Settings,
        brand_colors: list[str] | None = None,
    ) -> None:
        """Initialize the image generator.

        Args:
            client: OpenAI async client instance.
            settings: Pipeline settings.
            brand_colors: Optional hex color codes for placeholder generation.
        """
        self._client = client
        self._settings = settings
        self._brand_colors = brand_colors or ["#00A86B", "#1A1A2E"]
        self._primary_model = settings.image_model
        logger.debug(
            "ImageGenerator initialized: model=%s, quality=%s, max_retries=%d",
            self._primary_model,
            settings.dalle_quality,
            settings.max_retries,
        )

    async def generate(
        self,
        product: Product,
        brief: CampaignBrief,
        aspect_ratio: AspectRatio,
        output_dir: Path,
        *,
        skip_genai: bool = False,
        direction_fragment: str | None = None,
    ) -> tuple[Path, str]:
        """Generate or create an image for a product at a given aspect ratio.

        Args:
            product: Product to generate image for.
            brief: Campaign brief context.
            aspect_ratio: Target aspect ratio.
            output_dir: Directory to save the generated image.
            skip_genai: If True, skip API calls and go straight to placeholder.
            direction_fragment: Creative direction for the image prompt.

        Returns:
            Tuple of (path to saved image, source label).
            Source is one of: model name (e.g. 'gpt-image-1'), 'dall-e-2', or 'placeholder'.

        Raises:
            ImageGenerationError: If all generation methods fail and fallback is disabled.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        config = ASPECT_RATIO_CONFIG[aspect_ratio]
        prompt = _build_prompt(product, brief, direction_fragment)
        logger.debug("Built prompt for '%s' (%s): %s", product.name, aspect_ratio.value, prompt)

        if skip_genai:
            logger.info(
                "GenAI skipped for '%s' (%s) — generating placeholder",
                product.name,
                aspect_ratio.value,
            )
            return self._generate_placeholder(product, aspect_ratio, output_dir), "placeholder"

        # Tier 1: Primary model (gpt-image-1.5 by default)
        result = await self._try_dalle(
            prompt=prompt,
            model=self._primary_model,
            size=config["dalle_size"],
            quality=self._settings.dalle_quality,
            style=self._settings.image_style,
            output_dir=output_dir,
            product_name=product.name,
            aspect_ratio=aspect_ratio,
        )
        if result is not None:
            return result, self._primary_model

        # Tier 2: DALL-E 2 fallback (cheap, fast, always available)
        logger.warning(
            "%s failed for '%s' — falling back to dall-e-2",
            self._primary_model,
            product.name,
        )
        result = await self._try_dalle(
            prompt=prompt,
            model="dall-e-2",
            size="1024x1024",
            output_dir=output_dir,
            product_name=product.name,
            aspect_ratio=aspect_ratio,
        )
        if result is not None:
            return result, "dall-e-2"

        # Tier 3: Local placeholder
        logger.warning("All GenAI calls failed for '%s' — generating placeholder", product.name)
        if not self._settings.fallback_to_placeholder:
            raise ImageGenerationError(
                f"All image generation methods failed for '{product.name}'",
                detail=f"aspect_ratio={aspect_ratio.value}",
            )
        return self._generate_placeholder(product, aspect_ratio, output_dir), "placeholder"

    async def _try_dalle(
        self,
        *,
        prompt: str,
        model: str,
        size: str,
        quality: str | None = None,
        style: str | None = None,
        output_dir: Path,
        product_name: str,
        aspect_ratio: AspectRatio,
    ) -> Path | None:
        """Attempt DALL-E image generation with retries.

        Args:
            prompt: Image generation prompt.
            model: DALL-E model name.
            size: Image size string (e.g., '1024x1024').
            quality: Image quality setting (DALL-E 3 only).
            style: Image style setting (DALL-E 3 only).
            output_dir: Directory to save the image.
            product_name: Product name for file naming.
            aspect_ratio: Target aspect ratio.

        Returns:
            Path to saved image on success, None on failure.
        """
        max_retries = self._settings.max_retries
        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(
                    "DALL-E request: model=%s, size=%s, attempt=%d/%d",
                    model,
                    size,
                    attempt,
                    max_retries,
                )
                start = time.monotonic()

                # gpt-image-1 does NOT accept response_format (always returns b64)
                # gpt-image-1 uses quality: low/medium/high/auto
                # dall-e-3 uses quality: standard/hd and response_format: b64_json
                # dall-e-2 accepts response_format but has 1000 char prompt limit
                is_gpt_image = model.startswith("gpt-image")

                # Truncate prompt for DALL-E 2 (max 1000 chars)
                api_prompt = prompt
                if model == "dall-e-2" and len(prompt) > 1000:
                    api_prompt = prompt[:997] + "..."
                    logger.debug("Truncated prompt to 1000 chars for dall-e-2")

                kwargs: dict[str, str | int] = {
                    "model": model,
                    "prompt": api_prompt,
                    "size": size,
                    "n": 1,
                }

                if is_gpt_image:
                    # gpt-image-1 always returns b64 PNG by default — no extra params needed
                    # quality maps from our standard/hd config to low/medium/high
                    quality_map = {"standard": "medium", "hd": "high"}
                    kwargs["quality"] = quality_map.get(quality or "", "medium")
                elif model == "dall-e-3":
                    kwargs["response_format"] = "b64_json"
                    if quality:
                        kwargs["quality"] = quality
                    if style:
                        kwargs["style"] = style
                elif model == "dall-e-2":
                    kwargs["response_format"] = "b64_json"

                response = await asyncio.wait_for(
                    self._client.images.generate(**kwargs),  # type: ignore[arg-type]
                    timeout=self._settings.api_timeout_seconds,
                )
                elapsed = time.monotonic() - start
                logger.debug("DALL-E response received in %.1fs", elapsed)

                b64_data = response.data[0].b64_json
                if b64_data is None:
                    logger.warning("DALL-E returned no image data (attempt %d)", attempt)
                    continue

                image_bytes = base64.b64decode(b64_data)
                image = Image.open(io.BytesIO(image_bytes))
                file_name = f"hero_{model.replace('-', '_')}.png"
                save_path = output_dir / file_name
                image.save(str(save_path), "PNG")
                logger.info(
                    "Generated image for '%s' (%s) via %s in %.1fs: %s",
                    product_name,
                    aspect_ratio.value,
                    model,
                    elapsed,
                    save_path,
                )
                return save_path

            except TimeoutError:
                logger.warning(
                    "DALL-E %s timed out for '%s' (attempt %d/%d)",
                    model,
                    product_name,
                    attempt,
                    max_retries,
                )
            except Exception as exc:
                logger.warning(
                    "DALL-E %s error for '%s' (attempt %d/%d): %s",
                    model,
                    product_name,
                    attempt,
                    max_retries,
                    exc,
                )

            if attempt < max_retries:
                delay = 2**attempt
                logger.debug("Retrying in %ds...", delay)
                await asyncio.sleep(delay)

        return None

    def _generate_placeholder(
        self,
        product: Product,
        aspect_ratio: AspectRatio,
        output_dir: Path,
    ) -> Path:
        """Generate a local placeholder image with gradient background.

        Args:
            product: Product for text label.
            aspect_ratio: Target aspect ratio for dimensions.
            output_dir: Directory to save the placeholder.

        Returns:
            Path to the saved placeholder image.
        """
        config = ASPECT_RATIO_CONFIG[aspect_ratio]
        width, height = config["pixels"]
        color_top = hex_to_rgb(self._brand_colors[0])
        color_bottom = hex_to_rgb(
            self._brand_colors[1] if len(self._brand_colors) > 1 else self._brand_colors[0]
        )

        image = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(image)

        # Draw vertical gradient
        for y in range(height):
            ratio = y / max(height - 1, 1)
            r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
            g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
            b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Add product name text
        font_size = width // 15
        try:
            font = ImageFont.truetype("src/assets/fonts/Roboto-Bold.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        text = product.name.upper()
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = (width - text_w) // 2
        text_y = (height - text_h) // 2
        draw.text((text_x, text_y), text, fill="white", font=font)

        # Add "PLACEHOLDER" label
        small_size = width // 30
        try:
            small_font = ImageFont.truetype("src/assets/fonts/Roboto-Regular.ttf", small_size)
        except OSError:
            small_font = ImageFont.load_default()
        label = "PLACEHOLDER"
        label_bbox = draw.textbbox((0, 0), label, font=small_font)
        label_w = label_bbox[2] - label_bbox[0]
        draw.text(
            ((width - label_w) // 2, text_y + text_h + small_size),
            label,
            fill=(255, 255, 255, 180),
            font=small_font,
        )

        save_path = output_dir / "hero_placeholder.png"
        image.save(str(save_path), "PNG")
        logger.info(
            "Generated placeholder for '%s' (%s): %s", product.name, aspect_ratio.value, save_path
        )
        return save_path
