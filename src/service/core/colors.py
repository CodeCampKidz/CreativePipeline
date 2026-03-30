"""Shared color utilities."""

from __future__ import annotations

__all__ = ["hex_to_rgb"]


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex color string to an RGB tuple.

    Args:
        hex_color: Color in '#RRGGBB' format.

    Returns:
        Tuple of (red, green, blue) integers 0-255.
    """
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
