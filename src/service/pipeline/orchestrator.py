"""Main pipeline orchestrator — chains all stages with async execution."""

from __future__ import annotations

import asyncio
import json as json_mod
import time
from pathlib import Path
from typing import TYPE_CHECKING

from openai import AsyncOpenAI
from PIL import Image as PILImage
from slugify import slugify

from src.service.compliance.brand_checker import check_brand_compliance
from src.service.compliance.legal_checker import check_legal_content
from src.service.core.logger import get_logger, setup_logging
from src.service.integrations.creative_director import CreativeDirector
from src.service.integrations.image_generator import ImageGenerator
from src.service.integrations.localizer import translate_text
from src.service.integrations.message_generator import LANG_NAMES, MessageGenerator
from src.service.pipeline.asset_manager import AssetManager
from src.service.pipeline.image_processor import resize_and_crop
from src.service.pipeline.text_renderer import load_logo, render_text_overlay
from src.shared.models import (
    ASPECT_RATIO_CONFIG,
    AspectRatio,
    AssetResult,
    BrandComplianceResult,
    CampaignBrief,
    PipelineResult,
    PostMessage,
    ProductResult,
)

if TYPE_CHECKING:
    from PIL import Image

    from src.service.integrations.creative_director import CreativeDirection
    from src.shared.config import Settings
    from src.shared.models import BrandConfig, LegalCheckResult, Product

__all__ = ["Pipeline"]

logger = get_logger("pipeline")


class Pipeline:
    """Async pipeline orchestrator for creative asset generation.

    Stages:
        1. Brief validation (already done by caller)
        2. Legal content check
        3. Asset resolution per product
        4. GenAI image generation (for missing assets)
        5. Resize/crop per aspect ratio
        6. Text overlay + localization per language
        7. Brand compliance check + report
    """

    def __init__(
        self,
        settings: Settings,
        brief: CampaignBrief,
        brand_config: BrandConfig | None = None,
    ) -> None:
        """Initialize the pipeline.

        Args:
            settings: Application settings.
            brief: Validated campaign brief.
            brand_config: Optional brand configuration for compliance checks.
        """
        self._settings = settings
        self._brief = brief
        self._brand_config = brand_config
        self._campaign_slug = slugify(brief.campaign_name)
        self._campaign_dir = Path(settings.output_dir) / self._campaign_slug
        self._force_regenerate = False
        self._version_history: list[dict[str, object]] = []
        # _output_base is set per-run to the versioned directory
        self._output_base = self._campaign_dir

    @staticmethod
    def _load_version_history(campaign_dir: Path) -> list[dict[str, object]]:
        """Load creative outputs from all previous versions for context.

        Reads report.json from each existing version directory and extracts
        creative directions, post messages, and image sources so that
        subsequent versions can avoid repetition.

        Args:
            campaign_dir: Campaign root directory containing v1/, v2/, etc.

        Returns:
            List of version summaries, each containing direction and post messages.
        """
        history: list[dict[str, object]] = []
        if not campaign_dir.exists():
            return history

        for d in sorted(campaign_dir.iterdir()):
            if not (d.is_dir() and d.name.startswith("v") and d.name[1:].isdigit()):
                continue
            report_path = d / "report.json"
            if not report_path.exists():
                continue
            try:
                report = json_mod.loads(report_path.read_text(encoding="utf-8"))
                version_summary: dict[str, object] = {
                    "version": int(d.name[1:]),
                    "products": {},
                }
                for pr in report.get("products", []):
                    product_name = pr.get("product_name", "")
                    post_messages: list[dict[str, str]] = []
                    for asset in pr.get("assets", []):
                        pm = asset.get("post_message")
                        if pm:
                            post_messages.append(
                                {
                                    "language": pm.get("language", ""),
                                    "aspect_ratio": asset.get("aspect_ratio", ""),
                                    "text": pm.get("text", "")[:150],
                                    "platform": pm.get("platform_hint", ""),
                                }
                            )
                    version_summary["products"][product_name] = {  # type: ignore[index]
                        "post_messages": post_messages,
                    }
                history.append(version_summary)
                logger.debug("Loaded version history from %s", d.name)
            except Exception as exc:
                logger.warning("Failed to load version history from %s: %s", d.name, exc)

        return history

    @staticmethod
    def _format_history_for_director(history: list[dict[str, object]], product_name: str) -> str:
        """Format version history as context for the Creative Director prompt.

        Args:
            history: Previous version summaries.
            product_name: Product to extract history for.

        Returns:
            Formatted string for prompt injection, or empty string if no history.
        """
        if not history:
            return ""

        lines = ["Previous creative directions for this product (DO NOT repeat these):"]
        for vh in history:
            version = vh.get("version", "?")
            products = vh.get("products", {})
            if not isinstance(products, dict):
                continue
            product_data = products.get(product_name, {})
            if not isinstance(product_data, dict):
                continue
            messages = product_data.get("post_messages", [])
            if messages and isinstance(messages, list):
                sample = messages[0] if messages else {}
                if isinstance(sample, dict):
                    lines.append(f"  v{version}: post='{sample.get('text', '')[:80]}...'")

        if len(lines) <= 1:
            return ""

        return "\n".join(lines)

    @staticmethod
    def _format_history_for_messages(history: list[dict[str, object]], product_name: str) -> str:
        """Format version history as context for the Message Generator prompt.

        Args:
            history: Previous version summaries.
            product_name: Product to extract history for.

        Returns:
            Formatted string for prompt injection, or empty string if no history.
        """
        if not history:
            return ""

        lines = ["Post messages from previous versions (write something COMPLETELY DIFFERENT):"]
        for vh in history:
            version = vh.get("version", "?")
            products = vh.get("products", {})
            if not isinstance(products, dict):
                continue
            product_data = products.get(product_name, {})
            if not isinstance(product_data, dict):
                continue
            messages = product_data.get("post_messages", [])
            if isinstance(messages, list):
                for pm in messages:
                    if isinstance(pm, dict):
                        lines.append(
                            f"  v{version} ({pm.get('language', '?')}/{pm.get('aspect_ratio', '?')}): "
                            f"'{pm.get('text', '')[:100]}'"
                        )

        if len(lines) <= 1:
            return ""

        return "\n".join(lines)

    @staticmethod
    def _next_version(campaign_dir: Path) -> int:
        """Determine the next version number for a campaign.

        Args:
            campaign_dir: Campaign root directory (e.g., data/output/summer-splash-2026).

        Returns:
            Next version number (1 if no versions exist).
        """
        if not campaign_dir.exists():
            return 1
        existing = [
            int(d.name[1:])
            for d in campaign_dir.iterdir()
            if d.is_dir() and d.name.startswith("v") and d.name[1:].isdigit()
        ]
        return max(existing, default=0) + 1

    async def run(
        self,
        *,
        dry_run: bool = False,
        skip_genai: bool = False,
        force_regenerate: bool = False,
    ) -> PipelineResult:
        """Execute the full pipeline.

        Args:
            dry_run: If True, validate and plan but produce no output.
            skip_genai: If True, use placeholders instead of DALL-E.
            force_regenerate: If True, skip asset reuse for fresh creatives.

        Returns:
            PipelineResult with all generation details.
        """
        self._force_regenerate = force_regenerate
        start_time = time.monotonic()

        # Load previous version history for context (avoids repetition)
        self._version_history = self._load_version_history(self._campaign_dir)
        if self._version_history:
            logger.info(
                "Loaded %d previous version(s) for creative context",
                len(self._version_history),
            )

        # Determine versioned output directory
        version = self._next_version(self._campaign_dir)
        self._output_base = self._campaign_dir / f"v{version}"
        result = PipelineResult(
            campaign_name=self._brief.campaign_name,
            version=version,
        )

        # Set up logging to output directory
        log_file = self._output_base / "pipeline.log"
        if not dry_run:
            self._output_base.mkdir(parents=True, exist_ok=True)
            setup_logging(self._settings.log_level, log_file)

        logger.info("Starting pipeline for campaign: '%s'", self._brief.campaign_name)
        logger.info(
            "Products: %d, Ratios: %d, Languages: %d",
            len(self._brief.products),
            len(self._brief.aspect_ratios),
            len(self._brief.languages),
        )

        # Stage 2: Legal content check
        legal_result = await self._run_legal_check()
        result.legal_check = legal_result

        if dry_run:
            logger.info("Dry run — skipping asset generation")
            self._log_dry_run_plan()
            result.total_time_seconds = time.monotonic() - start_time
            return result

        # Stage 3-7: Process all products concurrently
        product_tasks = [
            self._process_product(product, skip_genai=skip_genai)
            for product in self._brief.products
        ]
        product_results = await asyncio.gather(*product_tasks, return_exceptions=True)

        for i, pr in enumerate(product_results):
            if isinstance(pr, Exception):
                product_name = self._brief.products[i].name
                error_msg = f"Product '{product_name}' failed: {pr}"
                logger.error(error_msg)
                result.errors.append(error_msg)
                result.products.append(ProductResult(product_name=product_name, errors=[str(pr)]))
            else:
                result.products.append(pr)

        # Aggregate counts
        for pr in result.products:
            for asset in pr.assets:
                if asset.source == "existing":
                    result.total_assets_reused += 1
                elif asset.source == "placeholder":
                    result.total_assets_placeholder += 1
                else:
                    result.total_assets_generated += 1

        result.total_time_seconds = time.monotonic() - start_time
        logger.info(
            "Pipeline complete: %d generated, %d reused, %d placeholders in %.1fs",
            result.total_assets_generated,
            result.total_assets_reused,
            result.total_assets_placeholder,
            result.total_time_seconds,
        )
        return result

    async def _run_legal_check(self) -> LegalCheckResult | None:
        """Run legal content check on campaign message.

        Returns:
            LegalCheckResult or None if no brand config.
        """
        if self._brand_config is None:
            logger.debug("No brand config — skipping legal check")
            return None

        try:
            legal_result = check_legal_content(
                self._brief.campaign_message,
                self._brand_config.prohibited_words,
            )
            if not legal_result.passed:
                logger.warning(
                    "Legal check flagged terms: %s",
                    [t["term"] for t in legal_result.flagged_terms],
                )
            else:
                logger.info("Legal content check: PASSED")
            return legal_result
        except Exception as exc:
            logger.warning("Legal check failed: %s — continuing pipeline", exc)
            return None

    async def _process_product(
        self,
        product: Product,
        *,
        skip_genai: bool,
    ) -> ProductResult:
        """Process a single product through stages 3-7.

        Args:
            product: Product to process.
            skip_genai: Whether to skip GenAI generation.

        Returns:
            ProductResult with all asset results.
        """
        product_slug = slugify(product.name)
        product_result = ProductResult(product_name=product.name)
        logger.info("Processing product: '%s'", product.name)

        # ── Sequential cumulative chain ──────────────────────────────────
        #
        # Stage A: Creative Director (original message → mood/style/tone/cultural angle)
        # Stage B: Post Messages (original message + direction → copy per lang/ratio)
        # Stage C: Per-language image (original message + direction + that lang's post copy)
        # Stage D: Per-language resize + text overlay per ratio
        #
        # Each language gets its own culturally tailored image because different
        # audiences respond to different visual cues, colors, and settings.

        # Stage A: Derive creative direction (1 LLM call)
        creative_direction = await self._derive_creative_direction(product)

        # Stage B: Generate ALL post messages (1 LLM call per ratio)
        all_post_messages: dict[tuple[str, str], PostMessage] = {}
        for ratio in self._brief.aspect_ratios:
            ratio_messages = await self._generate_post_messages(product, ratio, creative_direction)
            all_post_messages.update(ratio_messages)

        # Stage C: Generate one hero image PER LANGUAGE
        # Each image receives: original message + full creative direction + that
        # language's post message text, producing culturally tailored visuals.
        hero_images: dict[str, tuple[Image.Image, str]] = {}
        for lang in self._brief.languages:
            existing_path = None
            if not self._force_regenerate:
                asset_manager = AssetManager(Path(self._settings.input_assets_dir))
                existing_path = asset_manager.resolve(product.name, product.asset_folder)

            if existing_path is not None:
                try:
                    hero_images[lang] = (PILImage.open(str(existing_path)), "existing")
                    logger.info(
                        "Using existing asset for '%s' (%s): %s",
                        product.name,
                        lang,
                        existing_path,
                    )
                    continue
                except Exception as exc:
                    logger.warning(
                        "Failed to open asset %s: %s — will generate", existing_path, exc
                    )

            # Get this language's post message for image context
            lang_post_text = self._get_post_text_for_language(all_post_messages, lang)
            logger.info(
                "Generating culturally tailored image for '%s' (%s)",
                product.name,
                lang,
            )
            hero_image, source = await self._generate_hero(
                product,
                creative_direction=creative_direction,
                skip_genai=skip_genai,
                post_message_context=lang_post_text,
                language_hint=lang,
            )
            hero_images[lang] = (hero_image, source)

        # Stage D: Resize + text overlay per ratio/language
        ratio_tasks = [
            self._process_ratio(
                product,
                product_slug,
                hero_images,
                ratio,
                post_messages=all_post_messages,
            )
            for ratio in self._brief.aspect_ratios
        ]
        ratio_results = await asyncio.gather(*ratio_tasks, return_exceptions=True)

        for i, rr in enumerate(ratio_results):
            if isinstance(rr, Exception):
                ratio = self._brief.aspect_ratios[i]
                error_msg = f"Ratio {ratio.value} failed for '{product.name}': {rr}"
                logger.error(error_msg)
                product_result.errors.append(error_msg)
            elif isinstance(rr, list):
                product_result.assets.extend(rr)

        # Stage 7: Brand compliance check
        if self._brand_config is not None:
            product_result.brand_compliance = self._run_brand_check(product_slug)

        return product_result

    def _get_post_text_for_language(
        self, all_post_messages: dict[tuple[str, str], PostMessage], language: str
    ) -> str | None:
        """Extract post message text for a specific language.

        Args:
            all_post_messages: Dict of all generated post messages.
            language: ISO 639-1 language code.

        Returns:
            Post message text for that language, or None.
        """
        for ratio in self._brief.aspect_ratios:
            key = (language, ratio.value)
            if key in all_post_messages:
                msg = all_post_messages[key]
                if hasattr(msg, "text"):
                    return msg.text  # type: ignore[union-attr]
        return None

    def _get_primary_post_text(
        self, all_post_messages: dict[tuple[str, str], PostMessage]
    ) -> str | None:
        """Extract the primary (English, first ratio) post message text.

        Used as additional context for image generation so the image
        visually reflects what the post copy says.

        Args:
            all_post_messages: Dict of all generated post messages.

        Returns:
            English post message text, or None if unavailable.
        """
        # Prefer English + first ratio
        for ratio in self._brief.aspect_ratios:
            key = ("en", ratio.value)
            if key in all_post_messages:
                msg = all_post_messages[key]
                if hasattr(msg, "text"):
                    logger.debug("Primary post text for image context: '%s'", msg.text[:60])
                    return msg.text  # type: ignore[union-attr]

        # Fallback: any post message
        for msg in all_post_messages.values():
            if hasattr(msg, "text"):
                return msg.text  # type: ignore[union-attr]

        return None

    async def _generate_hero(
        self,
        product: Product,
        *,
        creative_direction: CreativeDirection | None = None,
        skip_genai: bool,
        post_message_context: str | None = None,
        language_hint: str | None = None,
    ) -> tuple[Image.Image, str]:
        """Generate a culturally tailored hero image for a product + language.

        Receives full cumulative context from the chain:
        - Creative direction: mood, style, scene, tone, cultural angle
        - Post message text for this specific language variant
        - Language hint for cultural tailoring

        Args:
            product: Product needing image generation.
            creative_direction: Creative direction for this product.
            skip_genai: Whether to skip API calls.
            post_message_context: Post message text for this language to inform the image.
            language_hint: ISO 639-1 language code for cultural tailoring.

        Returns:
            Tuple of (PIL Image, source label).
        """
        lang_suffix = f"_{language_hint}" if language_hint else ""
        staging_dir = self._output_base / "_staging" / f"{slugify(product.name)}{lang_suffix}"
        staging_dir.mkdir(parents=True, exist_ok=True)

        client = AsyncOpenAI(api_key=self._settings.openai_api_key)
        generator = ImageGenerator(
            client=client,
            settings=self._settings,
            brand_colors=(self._brand_config.primary_colors if self._brand_config else None),
        )

        # Build cumulative direction: all creative direction + post message + language
        direction_fragment = (
            creative_direction.to_image_prompt_fragment() if creative_direction else ""
        )

        if post_message_context:
            direction_fragment = (
                f"{direction_fragment} "
                f"The image should visually complement the themes and energy of the "
                f"accompanying social media post. Do NOT render any text into the image."
            )

        if language_hint and language_hint != "en":
            lang_name = LANG_NAMES.get(language_hint, language_hint)
            direction_fragment = (
                f"{direction_fragment} "
                f"This image targets a {lang_name}-speaking audience. "
                f"Tailor visual cues, colors, and cultural context to resonate with "
                f"{lang_name}-speaking consumers in {self._brief.target_region}."
            )

        hero_path, source = await generator.generate(
            product=product,
            brief=self._brief,
            aspect_ratio=AspectRatio.SQUARE,
            output_dir=staging_dir,
            skip_genai=skip_genai,
            direction_fragment=direction_fragment,
        )
        hero_image = PILImage.open(str(hero_path))
        return hero_image, source

    async def _process_ratio(
        self,
        product: Product,
        product_slug: str,
        hero_images: dict[str, tuple[Image.Image, str]],
        ratio: AspectRatio,
        *,
        post_messages: dict[tuple[str, str], PostMessage] | None = None,
    ) -> list[AssetResult]:
        """Process one aspect ratio for a product across all languages.

        Each language uses its own culturally tailored hero image.

        Args:
            product: Product being processed.
            product_slug: Slugified product name for folder structure.
            hero_images: Dict mapping language code to (hero_image, source) tuple.
            ratio: Target aspect ratio.
            post_messages: Pre-generated post messages keyed by (lang, ratio).

        Returns:
            List of AssetResult for each language variant.
        """
        if post_messages is None:
            post_messages = {}

        config = ASPECT_RATIO_CONFIG[ratio]
        ratio_folder = config["folder"]
        output_dir = self._output_base / product_slug / ratio_folder
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load logo once
        logo = None
        if self._brand_config and self._brand_config.logo_path:
            logo = await asyncio.to_thread(load_logo, self._brand_config.logo_path)

        # Process languages SEQUENTIALLY — each uses its own hero image
        results: list[AssetResult] = []
        elapsed_start = time.monotonic()

        for lang in self._brief.languages:
            try:
                # Get this language's hero image
                hero_image, source = hero_images.get(
                    lang,
                    hero_images.get("en", next(iter(hero_images.values()))),
                )

                # Resize this language's hero to the target ratio
                resized = await asyncio.to_thread(resize_and_crop, hero_image.copy(), ratio)
                lang_logo = logo.copy() if logo else None
                lp = await self._render_language(resized, lang_logo, lang, output_dir)
                elapsed = time.monotonic() - elapsed_start
                results.append(
                    AssetResult(
                        product_name=product.name,
                        aspect_ratio=ratio.value,
                        language=lang,
                        output_path=str(lp),
                        source=source,
                        generation_time_seconds=round(elapsed, 2),
                        post_message=post_messages.get((lang, ratio.value)),
                    )
                )
            except Exception as exc:
                logger.error(
                    "Language '%s' failed for '%s' %s: %s", lang, product.name, ratio.value, exc
                )

        return results

    async def _generate_post_messages(
        self,
        product: Product,
        ratio: AspectRatio,
        creative_direction: CreativeDirection | None = None,
    ) -> dict[tuple[str, str], PostMessage]:
        """Generate AI post messages for all languages at a given ratio.

        Makes a SINGLE LLM call that returns all language/ratio variants
        in structured JSON, ensuring language consistency.

        Args:
            product: Product to generate messages for.
            ratio: Aspect ratio (used to infer platform).

        Returns:
            Dict keyed by (language, ratio_value) with PostMessage values.
        """
        if not self._settings.openai_api_key:
            return {
                (lang, ratio.value): PostMessage(
                    text=self._brief.campaign_message,
                    hashtags=[],
                    platform_hint="general",
                    language=lang,
                )
                for lang in self._brief.languages
            }

        try:
            client = AsyncOpenAI(api_key=self._settings.openai_api_key)
            temp = 1.2 if self._force_regenerate else 0.8
            msg_gen = MessageGenerator(client, temperature=temp)
            copy_fragment = (
                creative_direction.to_copy_prompt_fragment() if creative_direction else None
            )
            history_context = self._format_history_for_messages(self._version_history, product.name)
            return await msg_gen.generate_all(
                product=product,
                brief=self._brief,
                languages=self._brief.languages,
                aspect_ratios=[ratio.value],
                direction_fragment=copy_fragment,
                history_context=history_context,
            )
        except Exception as exc:
            logger.warning("Post message generation failed: %s — using campaign message", exc)
            return {
                (lang, ratio.value): PostMessage(
                    text=self._brief.campaign_message,
                    hashtags=[],
                    platform_hint="general",
                    language=lang,
                )
                for lang in self._brief.languages
            }

    async def _derive_creative_direction(self, product: Product) -> CreativeDirection | None:
        """Derive creative direction for a product via the AI Creative Director.

        Args:
            product: Product to derive direction for.

        Returns:
            CreativeDirection instance, or None if unavailable.
        """
        if not self._settings.openai_api_key:
            logger.debug("No API key — skipping creative direction derivation")
            return None

        try:
            client = AsyncOpenAI(api_key=self._settings.openai_api_key)
            history_context = self._format_history_for_director(self._version_history, product.name)
            director = CreativeDirector(client)
            direction = await director.derive(product, self._brief, history_context=history_context)
            logger.info(
                "Creative direction for '%s': %s / %s",
                product.name,
                direction.visual_style[:50],
                direction.copy_tone[:50],
            )
            return direction
        except Exception as exc:
            logger.warning(
                "Creative direction failed for '%s': %s — using defaults", product.name, exc
            )
            return None

    async def _render_language(
        self,
        image: Image.Image,
        logo: Image.Image | None,
        language: str,
        output_dir: Path,
    ) -> Path:
        """Render text overlay for a specific language and save.

        Args:
            image: Resized image to overlay on.
            logo: Optional logo image.
            language: ISO 639-1 language code.
            output_dir: Directory to save the final creative.

        Returns:
            Path to the saved creative.
        """
        message = self._brief.campaign_message

        # Translate if not English
        if language != "en":
            try:
                message = await translate_text(message, language)
                logger.debug("Translated message to '%s': '%s'", language, message)
            except Exception as exc:
                logger.warning("Translation to '%s' failed: %s — using English", language, exc)
                message = self._brief.campaign_message

        font_path = self._brand_config.font_path if self._brand_config else None

        final = await asyncio.to_thread(render_text_overlay, image, message, logo, font_path)

        output_path = output_dir / f"creative_{language}.png"
        await asyncio.to_thread(final.save, str(output_path), "PNG")
        logger.info("Saved creative: %s", output_path)
        return output_path

    def _run_brand_check(self, product_slug: str) -> BrandComplianceResult:
        """Run brand compliance check for a product's creatives.

        Args:
            product_slug: Slugified product name.

        Returns:
            BrandComplianceResult.
        """
        try:
            product_dir = self._output_base / product_slug
            return check_brand_compliance(
                product_dir,
                self._brand_config,  # type: ignore[arg-type]
            )
        except Exception as exc:
            logger.warning("Brand check failed for '%s': %s", product_slug, exc)
            return BrandComplianceResult(
                status="error",
                logo_present=False,
                color_match_percentage=0.0,
                details=[f"Brand check error: {exc}"],
            )

    def _log_dry_run_plan(self) -> None:
        """Log the execution plan for dry-run mode."""
        logger.info("=== DRY RUN PLAN ===")
        for product in self._brief.products:
            asset_manager = AssetManager(Path(self._settings.input_assets_dir))
            existing = asset_manager.resolve(product.name, product.asset_folder)
            action = "REUSE existing" if existing else "GENERATE via GenAI"
            logger.info("  Product '%s': %s", product.name, action)
            for ratio in self._brief.aspect_ratios:
                for lang in self._brief.languages:
                    logger.info("    → %s / %s", ratio.value, lang)
        total = (
            len(self._brief.products) * len(self._brief.aspect_ratios) * len(self._brief.languages)
        )
        logger.info("Total creatives to generate: %d", total)
        logger.info("=== END DRY RUN ===")
