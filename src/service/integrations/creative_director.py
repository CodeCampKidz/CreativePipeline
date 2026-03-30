"""AI Creative Director — derives contextual creative direction from campaign briefs.

Stage 1 of a two-stage LLM chain. Analyzes the campaign brief and generates
a creative direction (visual style, tone, scene, mood) that is contextually
appropriate for the product, region, audience, and season.

Stage 2 consumers (image_generator, message_generator) use this direction
to produce varied but coherent creatives.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.service.core.logger import get_logger

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from src.shared.models import CampaignBrief, Product

__all__ = ["CreativeDirection", "CreativeDirector"]

logger = get_logger("creative_director")


@dataclass(frozen=True)
class CreativeDirection:
    """Contextual creative direction derived by the AI Creative Director."""

    visual_style: str
    lighting: str
    composition: str
    scene_setting: str
    mood: str
    color_palette_hint: str
    copy_tone: str
    copy_hook: str
    cultural_angle: str

    def to_image_prompt_fragment(self) -> str:
        """Format ALL creative direction fields as a prompt fragment for DALL-E."""
        return (
            f"Visual style: {self.visual_style}. "
            f"Composition: {self.composition} — product must dominate the frame. "
            f"Background/setting: {self.scene_setting} (subtle, not competing with product). "
            f"Lighting: {self.lighting}. "
            f"Mood and feel: {self.mood}. "
            f"Tone: {self.copy_tone} — the image should visually convey this tone. "
            f"Cultural angle: {self.cultural_angle} — reflect this in the visual context. "
            f"Color palette: {self.color_palette_hint}."
        )

    def to_copy_prompt_fragment(self) -> str:
        """Format as a prompt fragment for post message generation."""
        return (
            f"Tone: {self.copy_tone}. "
            f"Hook strategy: {self.copy_hook}. "
            f"Cultural angle: {self.cultural_angle}."
        )


# Fallback when LLM is unavailable
_DEFAULT_DIRECTION = CreativeDirection(
    visual_style="premium product hero photography, studio quality",
    lighting="soft studio lighting with subtle rim light to define product edges",
    composition="product centered as dominant element, filling 70% of frame",
    scene_setting="clean gradient or minimal surface that doesn't compete with product",
    mood="premium and aspirational",
    color_palette_hint="brand colors with clean white or neutral background",
    copy_tone="engaging and conversational",
    copy_hook="Start with a compelling statement about the product benefit",
    cultural_angle="universal appeal with local relevance",
)


class CreativeDirector:
    """Derives contextual creative direction from campaign context via LLM.

    Analyzes product, audience, region, and campaign message to produce
    a coherent creative direction that guides both image generation and
    post message copy. Each call produces a unique direction.
    """

    def __init__(self, client: AsyncOpenAI) -> None:
        """Initialize with an async OpenAI client.

        Args:
            client: OpenAI async client instance.
        """
        self._client = client

    async def derive(
        self,
        product: Product,
        brief: CampaignBrief,
        *,
        history_context: str = "",
    ) -> CreativeDirection:
        """Derive a creative direction for a product within a campaign.

        Args:
            product: The product to create direction for.
            brief: Campaign brief with full context.
            history_context: Formatted string of previous version outputs to avoid.

        Returns:
            CreativeDirection with all style/tone parameters.
        """
        logger.debug("Deriving creative direction for '%s'", product.name)

        system_prompt = (
            "You are an expert creative director at a top advertising agency specializing "
            "in product-focused social media advertising. Your job is to make the PRODUCT "
            "the unmistakable hero of every ad image. The product must be the largest, "
            "most prominent element — front and center, sharply focused, beautifully lit. "
            "Backgrounds and scenes exist only to complement and elevate the product. "
            "Never let people, crowds, or environments overshadow the product. "
            "Think: Apple product shots, Nike shoe hero shots, Dyson product photography. "
            "Each time you are called, produce a DIFFERENT creative angle."
        )

        user_prompt = (
            f"Derive a creative direction for a PRODUCT-FOCUSED social media ad:\n\n"
            f"Product: {product.name}\n"
            f"Product Description: {product.description}\n"
            f"Campaign: {brief.campaign_name}\n"
            f"Campaign Message: {brief.campaign_message}\n"
            f"Target Region: {brief.target_region}\n"
            f"Target Audience: {brief.target_audience}\n\n"
            f"CRITICAL RULES:\n"
            f"- The product MUST be the hero — largest element, front and center\n"
            f"- Composition must showcase the product, not a lifestyle scene\n"
            f"- People may appear but only as secondary elements, never dominating\n"
            f"- The image must make someone want to BUY this product\n\n"
            f"{history_context + chr(10) + chr(10) if history_context else ''}"
            f"Generate a UNIQUE creative direction. Respond in this exact JSON format:\n"
            f"{{\n"
            f'  "visual_style": "product-focused photography style (e.g., hero shot, studio, editorial)",\n'
            f'  "lighting": "lighting that makes the product look premium and desirable",\n'
            f'  "composition": "shot composition with product as dominant element (70%+ of frame)",\n'
            f'  "scene_setting": "backdrop/surface that elevates the product without competing",\n'
            f'  "mood": "emotional feel that drives purchase intent",\n'
            f'  "color_palette_hint": "colors that make the product pop",\n'
            f'  "copy_tone": "writing tone for the social media post text",\n'
            f'  "copy_hook": "how to open the post to drive engagement and purchase",\n'
            f'  "cultural_angle": "cultural reference for {brief.target_region} that connects to the product"\n'
            f"}}"
        )

        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=1.2,
                    max_tokens=400,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "creative_direction",
                            "strict": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "visual_style": {"type": "string"},
                                    "lighting": {"type": "string"},
                                    "composition": {"type": "string"},
                                    "scene_setting": {"type": "string"},
                                    "mood": {"type": "string"},
                                    "color_palette_hint": {"type": "string"},
                                    "copy_tone": {"type": "string"},
                                    "copy_hook": {"type": "string"},
                                    "cultural_angle": {"type": "string"},
                                },
                                "required": [
                                    "visual_style", "lighting", "composition",
                                    "scene_setting", "mood", "color_palette_hint",
                                    "copy_tone", "copy_hook", "cultural_angle",
                                ],
                                "additionalProperties": False,
                            },
                        },
                    },
                ),
                timeout=30,
            )

            content = response.choices[0].message.content or "{}"
            data = json.loads(content)

            direction = CreativeDirection(
                visual_style=data["visual_style"],
                lighting=data["lighting"],
                composition=data["composition"],
                scene_setting=data["scene_setting"],
                mood=data["mood"],
                color_palette_hint=data["color_palette_hint"],
                copy_tone=data["copy_tone"],
                copy_hook=data["copy_hook"],
                cultural_angle=data["cultural_angle"],
            )
            logger.info(
                "Creative direction for '%s': style=%s, mood=%s, tone=%s",
                product.name,
                direction.visual_style[:40],
                direction.mood[:40],
                direction.copy_tone[:40],
            )
            return direction

        except Exception as exc:
            logger.warning(
                "Creative direction derivation failed for '%s': %s — using defaults",
                product.name,
                exc,
            )
            return _DEFAULT_DIRECTION
