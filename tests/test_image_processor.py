"""Tests for image resize and smart center-crop logic."""

from __future__ import annotations

import pytest
from PIL import Image

from src.service.pipeline.image_processor import resize_and_crop
from src.shared.exceptions import ImageProcessingError
from src.shared.models import AspectRatio


class TestResizeAndCropPositive:
    """Positive resize/crop scenarios."""

    def test_square_to_square(self, sample_image: Image.Image) -> None:
        result = resize_and_crop(sample_image, AspectRatio.SQUARE)
        assert result.size == (1080, 1080)

    def test_square_to_portrait(self, sample_image: Image.Image) -> None:
        result = resize_and_crop(sample_image, AspectRatio.PORTRAIT)
        assert result.size == (1080, 1920)

    def test_square_to_landscape(self, sample_image: Image.Image) -> None:
        result = resize_and_crop(sample_image, AspectRatio.LANDSCAPE)
        assert result.size == (1920, 1080)

    def test_wide_image_cropped_to_square(self, wide_image: Image.Image) -> None:
        result = resize_and_crop(wide_image, AspectRatio.SQUARE)
        assert result.size == (1080, 1080)

    def test_tall_image_cropped_to_landscape(self, tall_image: Image.Image) -> None:
        result = resize_and_crop(tall_image, AspectRatio.LANDSCAPE)
        assert result.size == (1920, 1080)

    def test_large_image_downscaled(self) -> None:
        large = Image.new("RGB", (4000, 4000), color=(50, 50, 50))
        result = resize_and_crop(large, AspectRatio.SQUARE)
        assert result.size == (1080, 1080)

    def test_rgba_image_converted(self) -> None:
        rgba = Image.new("RGBA", (200, 200), color=(100, 150, 200, 255))
        result = resize_and_crop(rgba, AspectRatio.SQUARE)
        assert result.size == (1080, 1080)
        assert result.mode in ("RGB", "RGBA")

    def test_grayscale_image_converted(self) -> None:
        gray = Image.new("L", (200, 200), color=128)
        result = resize_and_crop(gray, AspectRatio.SQUARE)
        assert result.size == (1080, 1080)


class TestResizeAndCropNegative:
    """Negative resize/crop scenarios."""

    def test_zero_width_raises(self) -> None:
        # Create a degenerate image via crop
        img = Image.new("RGB", (10, 10))
        cropped = img.crop((5, 0, 5, 10))  # width=0
        with pytest.raises(ImageProcessingError, match="Invalid source image dimensions"):
            resize_and_crop(cropped, AspectRatio.SQUARE)

    def test_zero_height_raises(self) -> None:
        img = Image.new("RGB", (10, 10))
        cropped = img.crop((0, 5, 10, 5))  # height=0
        with pytest.raises(ImageProcessingError, match="Invalid source image dimensions"):
            resize_and_crop(cropped, AspectRatio.SQUARE)
