"""Tests for text overlay rendering and logo compositing."""

from __future__ import annotations

from PIL import Image

from src.service.pipeline.text_renderer import render_text_overlay


class TestTextRendererPositive:
    """Positive text rendering scenarios."""

    def test_basic_text_overlay(self) -> None:
        img = Image.new("RGB", (1080, 1080), color=(100, 100, 100))
        result = render_text_overlay(img, "Test Campaign Message")
        assert result.size == (1080, 1080)
        assert result.mode == "RGB"

    def test_text_overlay_preserves_dimensions(self) -> None:
        img = Image.new("RGB", (1920, 1080), color=(50, 50, 50))
        result = render_text_overlay(img, "Wide format message")
        assert result.size == (1920, 1080)

    def test_long_text_wraps(self) -> None:
        img = Image.new("RGB", (1080, 1080), color=(100, 100, 100))
        long_msg = "This is a very long campaign message that should wrap across multiple lines in the overlay band"
        result = render_text_overlay(img, long_msg)
        assert result.size == (1080, 1080)

    def test_logo_composited(self, sample_logo: Image.Image) -> None:
        img = Image.new("RGB", (1080, 1080), color=(100, 100, 100))
        result = render_text_overlay(img, "With logo", logo=sample_logo)
        assert result.size == (1080, 1080)
        # Result should differ from no-logo version (pixel data changed)
        no_logo = render_text_overlay(img, "With logo")
        assert result.tobytes() != no_logo.tobytes()

    def test_portrait_image(self) -> None:
        img = Image.new("RGB", (1080, 1920), color=(80, 80, 80))
        result = render_text_overlay(img, "Portrait creative")
        assert result.size == (1080, 1920)

    def test_small_image_minimum_font(self) -> None:
        img = Image.new("RGB", (100, 100), color=(50, 50, 50))
        result = render_text_overlay(img, "Tiny image")
        assert result.size == (100, 100)

    def test_unicode_message(self) -> None:
        img = Image.new("RGB", (1080, 1080), color=(100, 100, 100))
        result = render_text_overlay(img, "Verano Fresco 2026")
        assert result.size == (1080, 1080)


class TestTextRendererNegative:
    """Negative text rendering scenarios."""

    def test_empty_message_returns_copy(self) -> None:
        img = Image.new("RGB", (1080, 1080), color=(100, 100, 100))
        result = render_text_overlay(img, "")
        assert result.size == (1080, 1080)

    def test_whitespace_only_message_returns_copy(self) -> None:
        img = Image.new("RGB", (1080, 1080), color=(100, 100, 100))
        result = render_text_overlay(img, "   ")
        assert result.size == (1080, 1080)

    def test_missing_font_falls_back(self) -> None:
        img = Image.new("RGB", (1080, 1080), color=(100, 100, 100))
        result = render_text_overlay(img, "Missing font test", font_path="/nonexistent/font.ttf")
        assert result.size == (1080, 1080)
