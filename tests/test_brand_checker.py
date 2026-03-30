"""Tests for brand compliance checking."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.service.compliance.brand_checker import check_brand_compliance
from src.shared.models import BrandConfig


def _create_test_creative(path: Path, color: tuple[int, int, int]) -> None:
    """Create a solid-color test creative image."""
    img = Image.new("RGB", (100, 100), color=color)
    img.save(str(path))


class TestBrandCheckerPositive:
    """Positive brand compliance scenarios."""

    def test_on_brand_colors_pass(self, tmp_path: Path) -> None:
        brand = BrandConfig(
            brand_name="Test",
            primary_colors=["#00A86B"],  # RGB: (0, 168, 107)
            logo_path=str(tmp_path / "logo.png"),
        )
        # Create a fake logo
        Image.new("RGBA", (10, 10)).save(str(tmp_path / "logo.png"))

        # Create a creative with on-brand color
        product_dir = tmp_path / "product" / "1x1"
        product_dir.mkdir(parents=True)
        _create_test_creative(product_dir / "creative_en.png", (0, 160, 112))

        result = check_brand_compliance(tmp_path / "product", brand)
        assert result.logo_present is True
        assert result.status in ("pass", "warn")

    def test_logo_present_when_file_exists(self, tmp_path: Path) -> None:
        logo_path = tmp_path / "logo.png"
        Image.new("RGBA", (10, 10)).save(str(logo_path))
        brand = BrandConfig(
            brand_name="Test",
            primary_colors=["#FFFFFF"],
            logo_path=str(logo_path),
        )
        product_dir = tmp_path / "product" / "1x1"
        product_dir.mkdir(parents=True)
        _create_test_creative(product_dir / "creative_en.png", (255, 255, 255))

        result = check_brand_compliance(tmp_path / "product", brand)
        assert result.logo_present is True


class TestBrandCheckerNegative:
    """Negative brand compliance scenarios."""

    def test_off_brand_colors_flag(self, tmp_path: Path) -> None:
        brand = BrandConfig(
            brand_name="Test",
            primary_colors=["#00A86B"],  # Green
            logo_path=str(tmp_path / "missing_logo.png"),
        )
        product_dir = tmp_path / "product" / "1x1"
        product_dir.mkdir(parents=True)
        # Bright red — very off-brand from green
        _create_test_creative(product_dir / "creative_en.png", (255, 0, 0))

        result = check_brand_compliance(tmp_path / "product", brand)
        assert result.logo_present is False
        # Off-brand colors should not pass
        assert result.color_match_percentage < 100

    def test_no_creatives_warns(self, tmp_path: Path) -> None:
        brand = BrandConfig(
            brand_name="Test",
            primary_colors=["#FFFFFF"],
            logo_path=str(tmp_path / "logo.png"),
        )
        empty_dir = tmp_path / "product"
        empty_dir.mkdir()

        result = check_brand_compliance(empty_dir, brand)
        assert result.status == "warn"
        assert any("No creative" in d for d in result.details)

    def test_missing_logo_flagged(self, tmp_path: Path) -> None:
        brand = BrandConfig(
            brand_name="Test",
            primary_colors=["#FFFFFF"],
            logo_path="/nonexistent/logo.png",
        )
        product_dir = tmp_path / "product" / "1x1"
        product_dir.mkdir(parents=True)
        _create_test_creative(product_dir / "creative_en.png", (255, 255, 255))

        result = check_brand_compliance(tmp_path / "product", brand)
        assert result.logo_present is False
