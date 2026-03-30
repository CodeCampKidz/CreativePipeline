"""Shared test fixtures for the Creative Automation Pipeline test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from src.shared.models import AspectRatio, CampaignBrief, Product


@pytest.fixture
def sample_brief_dict() -> dict[str, Any]:
    """Raw dictionary representing a valid campaign brief."""
    return {
        "campaign_name": "Test Campaign 2026",
        "products": [
            {
                "name": "Eco Bottle",
                "description": "Sustainable reusable water bottle",
                "asset_folder": "input_assets/eco_bottle",
            },
            {
                "name": "Sport Cap",
                "description": "Lightweight breathable sports cap",
                "asset_folder": "input_assets/sport_cap",
            },
        ],
        "target_region": "Latin America",
        "target_audience": "Health-conscious millennials 25-35",
        "campaign_message": "Stay Fresh. Stay Green.",
        "languages": ["en", "es"],
        "aspect_ratios": ["1:1", "9:16", "16:9"],
    }


@pytest.fixture
def sample_brief(sample_brief_dict: dict[str, Any]) -> CampaignBrief:
    """Validated CampaignBrief model instance."""
    return CampaignBrief.model_validate(sample_brief_dict)


@pytest.fixture
def sample_product() -> Product:
    """A single Product model instance."""
    return Product(
        name="Eco Bottle",
        description="Sustainable reusable water bottle",
        asset_folder="input_assets/eco_bottle",
    )


@pytest.fixture
def sample_image() -> Image.Image:
    """A small 200x200 solid-color test image."""
    return Image.new("RGB", (200, 200), color=(100, 150, 200))


@pytest.fixture
def sample_logo() -> Image.Image:
    """A small 50x50 RGBA logo image for testing compositing."""
    logo = Image.new("RGBA", (50, 50), color=(0, 168, 107, 255))
    return logo


@pytest.fixture
def wide_image() -> Image.Image:
    """A 400x200 landscape image for crop testing."""
    return Image.new("RGB", (400, 200), color=(200, 100, 50))


@pytest.fixture
def tall_image() -> Image.Image:
    """A 200x400 portrait image for crop testing."""
    return Image.new("RGB", (200, 400), color=(50, 100, 200))


@pytest.fixture
def sample_brief_yaml(tmp_path: Path, sample_brief_dict: dict[str, Any]) -> Path:
    """Write a valid brief to a temporary YAML file and return its path."""
    import yaml

    brief_path = tmp_path / "brief.yaml"
    brief_path.write_text(yaml.dump(sample_brief_dict), encoding="utf-8")
    return brief_path


@pytest.fixture
def sample_brief_json(tmp_path: Path, sample_brief_dict: dict[str, Any]) -> Path:
    """Write a valid brief to a temporary JSON file and return its path."""
    import json

    brief_path = tmp_path / "brief.json"
    brief_path.write_text(json.dumps(sample_brief_dict), encoding="utf-8")
    return brief_path


@pytest.fixture
def invalid_brief_dict() -> dict[str, Any]:
    """Dictionary with only one product (invalid)."""
    return {
        "campaign_name": "Bad Campaign",
        "products": [
            {"name": "Only One", "description": "Single product"},
        ],
        "target_region": "US",
        "target_audience": "Everyone",
        "campaign_message": "Buy now",
    }


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    """Temporary output directory for pipeline results."""
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def tmp_input_assets(tmp_path: Path, sample_image: Image.Image) -> Path:
    """Temporary input assets directory with one existing asset."""
    assets_dir = tmp_path / "input_assets"
    eco_dir = assets_dir / "eco_bottle"
    eco_dir.mkdir(parents=True)
    hero_path = eco_dir / "hero.png"
    sample_image.save(str(hero_path))

    sport_dir = assets_dir / "sport_cap"
    sport_dir.mkdir(parents=True)
    # sport_cap has no hero image — triggers generation

    return assets_dir


@pytest.fixture
def all_aspect_ratios() -> list[AspectRatio]:
    """All three supported aspect ratios."""
    return [AspectRatio.SQUARE, AspectRatio.PORTRAIT, AspectRatio.LANDSCAPE]
