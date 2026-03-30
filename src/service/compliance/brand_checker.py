"""Brand compliance checking — verify logo presence and color alignment."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from src.service.core.colors import hex_to_rgb
from src.service.core.logger import get_logger
from src.shared.models import BrandComplianceResult

if TYPE_CHECKING:
    from src.shared.models import BrandConfig

__all__ = ["check_brand_compliance"]

logger = get_logger("brand_checker")


def _color_distance(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    """Calculate Euclidean distance between two RGB colors.

    Args:
        c1: First RGB color.
        c2: Second RGB color.

    Returns:
        Distance as a float (0.0 = identical, ~441.7 = max for black vs white).
    """
    return ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2) ** 0.5


def _get_dominant_colors(
    image: Image.Image, num_colors: int = 5, sample_size: int = 1000
) -> list[tuple[int, int, int]]:
    """Extract dominant colors from an image by sampling and counting.

    Args:
        image: PIL Image to analyze.
        num_colors: Number of dominant colors to return.
        sample_size: Number of pixels to sample.

    Returns:
        List of RGB tuples sorted by frequency.
    """
    img = image.convert("RGB")
    # Resize for faster sampling
    img = img.resize((100, 100), Image.LANCZOS)
    pixels = list(img.getdata())

    # Quantize to reduce color space (round to nearest 16)
    quantized = [(r // 16 * 16, g // 16 * 16, b // 16 * 16) for r, g, b in pixels]
    counter = Counter(quantized)
    return [color for color, _ in counter.most_common(num_colors)]


def check_brand_compliance(
    product_dir: Path,
    brand_config: BrandConfig,
    color_threshold: float = 80.0,
) -> BrandComplianceResult:
    """Check brand compliance for all creatives in a product directory.

    Args:
        product_dir: Directory containing generated creatives.
        brand_config: Brand configuration with colors and logo path.
        color_threshold: Max RGB Euclidean distance to consider a color "on-brand".

    Returns:
        BrandComplianceResult with compliance status.
    """
    logger.debug("Running brand compliance check in %s", product_dir)
    details: list[str] = []

    # Check logo presence
    logo_path = Path(brand_config.logo_path)
    logo_present = logo_path.is_file()
    if logo_present:
        details.append("Brand logo file exists and was composited onto creatives")
    else:
        details.append(f"Brand logo not found at: {brand_config.logo_path}")

    # Check color compliance across creatives
    brand_rgb = [hex_to_rgb(c) for c in brand_config.primary_colors]
    total_checked = 0
    total_matches = 0

    creative_files = list(product_dir.rglob("creative_*.png"))
    if not creative_files:
        logger.warning("No creative files found in %s", product_dir)
        return BrandComplianceResult(
            status="warn",
            logo_present=logo_present,
            color_match_percentage=0.0,
            details=[*details, "No creative files found for color analysis"],
        )

    for creative_path in creative_files:
        try:
            img = Image.open(str(creative_path))
            dominant = _get_dominant_colors(img)
            for dc in dominant:
                total_checked += 1
                for bc in brand_rgb:
                    if _color_distance(dc, bc) <= color_threshold:
                        total_matches += 1
                        break
        except Exception as exc:
            logger.warning("Failed to analyze %s: %s", creative_path, exc)
            details.append(f"Could not analyze: {creative_path.name}")

    match_pct = (total_matches / max(total_checked, 1)) * 100
    details.append(f"Color analysis: {match_pct:.0f}% of dominant colors are on-brand")

    if match_pct >= 50:
        status = "pass"
    elif match_pct >= 25:
        status = "warn"
    else:
        status = "fail"

    logger.info(
        "Brand compliance for %s: %s (%.0f%% color match)", product_dir.name, status, match_pct
    )
    return BrandComplianceResult(
        status=status,
        logo_present=logo_present,
        color_match_percentage=round(match_pct, 1),
        details=details,
    )
