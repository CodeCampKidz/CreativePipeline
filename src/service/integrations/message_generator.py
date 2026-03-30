"""AI-powered social media post message generation via OpenAI chat completion.

Generates all language/ratio variants in a single structured LLM call per product.
The LLM returns a JSON array with one entry per language+ratio combination,
ensuring language consistency and eliminating per-variant API overhead.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from src.service.core.logger import get_logger
from src.shared.models import PostMessage

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from src.shared.models import CampaignBrief, Product

__all__ = ["MessageGenerator"]

logger = get_logger("message_generator")

# Platform inferred from aspect ratio
RATIO_PLATFORM_MAP = {
    "1:1": "Instagram Feed / Facebook",
    "9:16": "Instagram Stories / TikTok / Reels",
    "16:9": "YouTube / Facebook / LinkedIn",
}

# Human-readable language names
LANG_NAMES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
    "hi": "Hindi",
    "ru": "Russian",
}


class MessageGenerator:
    """Generates all post message variants for a product in a single LLM call.

    Given a product, campaign brief, list of languages, and list of aspect ratios,
    makes one OpenAI chat completion call that returns a structured JSON array
    with a post message for every language+ratio combination.
    """

    def __init__(self, client: AsyncOpenAI, *, temperature: float = 0.8) -> None:
        """Initialize with an async OpenAI client.

        Args:
            client: OpenAI async client instance.
            temperature: Sampling temperature for creative variety.
        """
        self._client = client
        self._temperature = temperature

    async def generate_all(
        self,
        product: Product,
        brief: CampaignBrief,
        languages: list[str],
        aspect_ratios: list[str],
        *,
        direction_fragment: str | None = None,
        history_context: str = "",
    ) -> dict[tuple[str, str], PostMessage]:
        """Generate post messages for all language/ratio combinations in one call.

        Args:
            product: Product to generate messages for.
            brief: Campaign brief context.
            languages: List of ISO 639-1 language codes.
            aspect_ratios: List of aspect ratio strings.
            direction_fragment: Optional copy direction from CreativeDirector.
            history_context: Previous versions' post messages to avoid repeating.

        Returns:
            Dict keyed by (language, aspect_ratio) with PostMessage values.
        """
        # Build the variant list the LLM must fill
        variants_spec = []
        for lang in languages:
            for ratio in aspect_ratios:
                platform = RATIO_PLATFORM_MAP.get(ratio, "social media")
                lang_name = LANG_NAMES.get(lang, lang)
                variants_spec.append(
                    {
                        "language_code": lang,
                        "language_name": lang_name,
                        "aspect_ratio": ratio,
                        "platform": platform,
                    }
                )

        lang_list = ", ".join(f"{LANG_NAMES.get(lc, lc)} ({lc})" for lc in languages)

        system_prompt = (
            "You are a world-class social media copywriter for a global consumer goods brand. "
            "You write engaging, culturally relevant post messages in MULTIPLE languages. "
            "When writing in different languages, each version must be a NATIVE-QUALITY message "
            "in that language — not a translation. English posts use English idioms, "
            "Spanish posts use Spanish idioms, etc."
        )

        direction_block = (
            f"\nCreative Direction:\n{direction_fragment}\n" if direction_fragment else ""
        )

        # Build JSON schema example
        example_entry = (
            '{"language": "en", "aspect_ratio": "1:1", "platform": "Instagram Feed", '
            '"text": "the post message", "hashtags": ["#tag1", "#tag2"]}'
        )

        user_prompt = (
            f"Generate social media post messages for this product campaign.\n\n"
            f"Product: {product.name}\n"
            f"Product Description: {product.description}\n"
            f"Campaign: {brief.campaign_name}\n"
            f"Campaign Message: {brief.campaign_message}\n"
            f"Target Region: {brief.target_region}\n"
            f"Target Audience: {brief.target_audience}\n"
            f"{direction_block}\n"
            f"Generate ONE post message for EACH of these {len(variants_spec)} combinations:\n\n"
        )

        for i, v in enumerate(variants_spec, 1):
            user_prompt += (
                f"  {i}. {v['language_name']} ({v['language_code']}) — "
                f"{v['aspect_ratio']} — {v['platform']}\n"
            )

        history_block = f"\n{history_context}\n" if history_context else ""

        user_prompt += (
            f"\nRules:\n"
            f"- Each message MUST be written in its specified language\n"
            f"- {lang_list} — keep each language authentic, not translated\n"
            f"- Max 280 characters per message\n"
            f"- Include 3-5 relevant hashtags per message (in the same language)\n"
            f"- Each message should complement a visual product ad for {product.name}\n"
            f"- Vary the tone/angle across different aspect ratios\n"
            f"{history_block}\n"
            f"Respond with exactly this JSON format:\n"
            f'{{"variants": [{example_entry}, ...]}}\n\n'
            f"Return exactly {len(variants_spec)} variants."
        )

        logger.debug(
            "Generating %d post message variants for '%s' in one call",
            len(variants_spec),
            product.name,
        )

        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self._temperature,
                    max_tokens=1500,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "post_messages",
                            "strict": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "variants": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "language": {"type": "string"},
                                                "aspect_ratio": {"type": "string"},
                                                "platform": {"type": "string"},
                                                "text": {"type": "string"},
                                                "hashtags": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                            },
                                            "required": [
                                                "language", "aspect_ratio",
                                                "platform", "text", "hashtags",
                                            ],
                                            "additionalProperties": False,
                                        },
                                    },
                                },
                                "required": ["variants"],
                                "additionalProperties": False,
                            },
                        },
                    },
                ),
                timeout=45,
            )

            content = response.choices[0].message.content or '{"variants": []}'
            data = json.loads(content)
            variants = data["variants"]

            results: dict[tuple[str, str], PostMessage] = {}
            for v in variants:
                lang = v["language"]
                ratio = v["aspect_ratio"]
                # Always use OUR platform mapping — never trust the LLM's value
                platform = RATIO_PLATFORM_MAP.get(ratio, "social media")
                key = (lang, ratio)
                results[key] = PostMessage(
                    text=v["text"],
                    hashtags=v["hashtags"],
                    platform_hint=platform,
                    language=lang,
                )

            logger.info(
                "Generated %d/%d post message variants for '%s'",
                len(results),
                len(variants_spec),
                product.name,
            )

            # Fill any missing variants with campaign message fallback
            for v_spec in variants_spec:
                key = (v_spec["language_code"], v_spec["aspect_ratio"])
                if key not in results:
                    logger.warning(
                        "Missing variant %s for '%s' — using fallback", key, product.name
                    )
                    results[key] = PostMessage(
                        text=brief.campaign_message,
                        hashtags=[],
                        platform_hint=v_spec["platform"],
                        language=v_spec["language_code"],
                    )

            return results

        except Exception as exc:
            logger.warning(
                "Post message generation failed for '%s': %s — using campaign message for all",
                product.name,
                exc,
            )
            return {
                (v["language_code"], v["aspect_ratio"]): PostMessage(
                    text=brief.campaign_message,
                    hashtags=[],
                    platform_hint=v["platform"],
                    language=v["language_code"],
                )
                for v in variants_spec
            }
