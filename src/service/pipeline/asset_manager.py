"""Asset resolution — find existing hero images or flag for generation."""

from __future__ import annotations

from pathlib import Path

from src.service.core.logger import get_logger

__all__ = ["AssetManager"]

logger = get_logger("asset_manager")

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class AssetManager:
    """Resolves existing assets for products from a local directory.

    For each product, checks its asset_folder for a usable hero image.
    If found, returns the path; otherwise returns None to trigger generation.
    """

    def __init__(self, base_dir: Path) -> None:
        """Initialize with the base input assets directory.

        Args:
            base_dir: Root directory containing per-product asset folders.
        """
        self._base_dir = base_dir
        logger.debug("AssetManager initialized with base_dir=%s", base_dir)

    def resolve(self, product_name: str, asset_folder: str | None) -> Path | None:
        """Attempt to find an existing hero image for a product.

        Args:
            product_name: Display name of the product (used for logging).
            asset_folder: Relative or absolute path to the product's asset folder.

        Returns:
            Path to the hero image if found, None otherwise.
        """
        logger.debug("Resolving asset for product='%s', folder='%s'", product_name, asset_folder)

        if asset_folder is None:
            logger.info("No asset folder specified for '%s' — will generate", product_name)
            return None

        folder = Path(asset_folder)
        if not folder.is_absolute():
            folder = self._base_dir / folder.name

        # Prevent path traversal — resolved path must be within base directory
        try:
            folder = folder.resolve()
            if not str(folder).startswith(str(self._base_dir.resolve())):
                logger.warning(
                    "Path traversal blocked for '%s': %s escapes %s",
                    product_name,
                    folder,
                    self._base_dir,
                )
                return None
        except OSError:
            return None

        if not folder.exists():
            logger.info(
                "Asset folder does not exist for '%s': %s — will generate",
                product_name,
                folder,
            )
            return None

        if not folder.is_dir():
            logger.warning(
                "Asset path is not a directory for '%s': %s — will generate",
                product_name,
                folder,
            )
            return None

        # Look for hero image by convention: hero.png, hero.jpg, etc.
        for ext in SUPPORTED_IMAGE_EXTENSIONS:
            hero_path = folder / f"hero{ext}"
            if hero_path.is_file():
                logger.info("Found existing asset for '%s': %s", product_name, hero_path)
                return hero_path

        # Fallback: first image file in the folder
        for child in sorted(folder.iterdir()):
            if child.is_file() and child.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                logger.info("Found existing asset for '%s' (fallback): %s", product_name, child)
                return child

        logger.info("No usable asset found for '%s' in %s — will generate", product_name, folder)
        return None
