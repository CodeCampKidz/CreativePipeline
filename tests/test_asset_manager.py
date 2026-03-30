"""Tests for asset resolution logic."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.service.pipeline.asset_manager import AssetManager


class TestAssetManagerPositive:
    """Positive scenarios for asset resolution."""

    def test_finds_hero_png(self, tmp_input_assets: Path) -> None:
        manager = AssetManager(tmp_input_assets)
        result = manager.resolve("Eco Bottle", "input_assets/eco_bottle")
        assert result is not None
        assert result.name == "hero.png"

    def test_finds_hero_jpg_fallback(self, tmp_path: Path) -> None:
        product_dir = tmp_path / "input_assets" / "widget"
        product_dir.mkdir(parents=True)
        img = Image.new("RGB", (10, 10))
        img.save(str(product_dir / "hero.jpg"))

        manager = AssetManager(tmp_path / "input_assets")
        result = manager.resolve("Widget", "input_assets/widget")
        assert result is not None
        assert result.suffix == ".jpg"

    def test_finds_first_image_when_no_hero(self, tmp_path: Path) -> None:
        product_dir = tmp_path / "input_assets" / "gadget"
        product_dir.mkdir(parents=True)
        img = Image.new("RGB", (10, 10))
        img.save(str(product_dir / "banner.png"))

        manager = AssetManager(tmp_path / "input_assets")
        result = manager.resolve("Gadget", "input_assets/gadget")
        assert result is not None
        assert result.name == "banner.png"

    def test_returns_none_for_empty_folder(self, tmp_input_assets: Path) -> None:
        manager = AssetManager(tmp_input_assets)
        result = manager.resolve("Sport Cap", "input_assets/sport_cap")
        assert result is None

    def test_returns_none_when_no_folder_specified(self, tmp_input_assets: Path) -> None:
        manager = AssetManager(tmp_input_assets)
        result = manager.resolve("Unknown", None)
        assert result is None


class TestAssetManagerNegative:
    """Negative scenarios for asset resolution."""

    def test_nonexistent_folder_returns_none(self, tmp_path: Path) -> None:
        manager = AssetManager(tmp_path)
        result = manager.resolve("Missing", "input_assets/nonexistent")
        assert result is None

    def test_file_instead_of_dir_returns_none(self, tmp_path: Path) -> None:
        assets_dir = tmp_path / "input_assets"
        assets_dir.mkdir()
        # Create a file where a directory is expected
        fake = assets_dir / "not_a_dir"
        fake.write_text("not a directory")

        manager = AssetManager(assets_dir)
        result = manager.resolve("Bad", "input_assets/not_a_dir")
        assert result is None

    def test_folder_with_only_non_image_files(self, tmp_path: Path) -> None:
        product_dir = tmp_path / "input_assets" / "textonly"
        product_dir.mkdir(parents=True)
        (product_dir / "readme.txt").write_text("not an image")
        (product_dir / "data.csv").write_text("a,b,c")

        manager = AssetManager(tmp_path / "input_assets")
        result = manager.resolve("TextOnly", "input_assets/textonly")
        assert result is None
