"""Storage abstraction — local filesystem and AWS S3 backends."""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from src.service.core.logger import get_logger

if TYPE_CHECKING:
    from src.shared.config import Settings

__all__ = [
    "LocalStorage",
    "S3Storage",
    "StorageBackend",
    "create_storage",
    "delete_from_storage",
    "sync_to_storage",
]

logger = get_logger("storage")


class StorageBackend(ABC):
    """Abstract base class for asset storage backends."""

    @abstractmethod
    def save(self, local_path: Path, destination_key: str) -> str:
        """Save a local file to the storage backend.

        Args:
            local_path: Path to the local file to upload.
            destination_key: Logical destination path/key in storage.

        Returns:
            URI or path where the file was stored.
        """

    @abstractmethod
    def list_assets(self, prefix: str) -> list[str]:
        """List stored assets under a prefix.

        Args:
            prefix: Storage key prefix to list.

        Returns:
            List of asset keys/paths.
        """

    @abstractmethod
    def delete(self, prefix: str) -> int:
        """Delete all stored assets under a prefix.

        Args:
            prefix: Storage key prefix to delete.

        Returns:
            Number of assets deleted.
        """

    @abstractmethod
    def get_uri(self, key: str) -> str:
        """Get the access URI for a stored asset.

        Args:
            key: Storage key for the asset.

        Returns:
            URI string (file path, S3 URL, etc.).
        """


class LocalStorage(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_dir: str = "output") -> None:
        """Initialize local storage.

        Args:
            base_dir: Base directory for stored assets.
        """
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("LocalStorage initialized: base_dir=%s", self._base_dir)

    def save(self, local_path: Path, destination_key: str) -> str:
        """Copy a local file to the output directory.

        Args:
            local_path: Source file path.
            destination_key: Relative destination path.

        Returns:
            Absolute path to the stored file.
        """
        dest = self._base_dir / destination_key
        dest.parent.mkdir(parents=True, exist_ok=True)

        if local_path.resolve() != dest.resolve():
            shutil.copy2(str(local_path), str(dest))
            logger.debug("LocalStorage saved: %s -> %s", local_path, dest)

        return str(dest)

    def list_assets(self, prefix: str) -> list[str]:
        """List files under a prefix in the base directory.

        Args:
            prefix: Relative directory prefix.

        Returns:
            List of relative file paths.
        """
        target = self._base_dir / prefix
        if not target.exists():
            return []
        return [str(p.relative_to(self._base_dir)) for p in target.rglob("*") if p.is_file()]

    def delete(self, prefix: str) -> int:
        """Delete all files under a prefix in the base directory.

        Args:
            prefix: Relative directory prefix to delete.

        Returns:
            Number of files deleted.
        """
        target = self._base_dir / prefix
        if not target.exists():
            return 0
        files = [p for p in target.rglob("*") if p.is_file()]
        count = len(files)
        shutil.rmtree(target)
        logger.debug("LocalStorage deleted %d files under %s", count, prefix)
        return count

    def get_uri(self, key: str) -> str:
        """Get local file path as URI.

        Args:
            key: Relative path in storage.

        Returns:
            Absolute file path string.
        """
        return str(self._base_dir / key)


class S3Storage(StorageBackend):
    """AWS S3 storage backend."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "campaigns/",
        region: str = "us-east-1",
        aws_access_key_id: str = "",
        aws_secret_access_key: str = "",
    ) -> None:
        """Initialize S3 storage.

        Args:
            bucket: S3 bucket name.
            prefix: Key prefix for all stored assets.
            region: AWS region.
            aws_access_key_id: AWS access key (falls back to boto3 credential chain if empty).
            aws_secret_access_key: AWS secret key.
        """
        import boto3

        self._bucket = bucket
        self._prefix = prefix
        kwargs: dict[str, str] = {"region_name": region}
        if aws_access_key_id and aws_secret_access_key:
            kwargs["aws_access_key_id"] = aws_access_key_id
            kwargs["aws_secret_access_key"] = aws_secret_access_key
        self._client = boto3.client("s3", **kwargs)
        logger.info(
            "S3Storage initialized: bucket=%s, prefix=%s, region=%s", bucket, prefix, region
        )

    def save(self, local_path: Path, destination_key: str) -> str:
        """Upload a local file to S3.

        Args:
            local_path: Source file path.
            destination_key: S3 key suffix (prefix is prepended).

        Returns:
            S3 URI of the uploaded object.
        """
        s3_key = f"{self._prefix}{destination_key}"
        try:
            self._client.upload_file(
                str(local_path),
                self._bucket,
                s3_key,
                ExtraArgs={"ContentType": "image/png"},
            )
            uri = f"s3://{self._bucket}/{s3_key}"
            logger.info("S3Storage uploaded: %s -> %s", local_path, uri)
            return uri
        except Exception as exc:
            logger.error("S3 upload failed for %s: %s", s3_key, exc)
            raise

    def list_assets(self, prefix: str) -> list[str]:
        """List objects under a prefix in S3.

        Args:
            prefix: Key prefix to list.

        Returns:
            List of S3 object keys.
        """
        full_prefix = f"{self._prefix}{prefix}"
        try:
            response = self._client.list_objects_v2(Bucket=self._bucket, Prefix=full_prefix)
            contents = response.get("Contents", [])
            return [obj["Key"] for obj in contents]
        except Exception as exc:
            logger.error("S3 list failed for prefix %s: %s", full_prefix, exc)
            return []

    def delete(self, prefix: str) -> int:
        """Delete all objects under a prefix in S3.

        Args:
            prefix: Key prefix to delete.

        Returns:
            Number of objects deleted.
        """
        full_prefix = f"{self._prefix}{prefix}"
        try:
            deleted = 0
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=full_prefix):
                objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if objects:
                    self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": objects})
                    deleted += len(objects)
            logger.info("S3Storage deleted %d objects under %s", deleted, full_prefix)
            return deleted
        except Exception as exc:
            logger.error("S3 delete failed for prefix %s: %s", full_prefix, exc)
            raise

    def get_uri(self, key: str) -> str:
        """Get S3 URI for a stored asset.

        Args:
            key: S3 object key.

        Returns:
            S3 URI string.
        """
        return f"s3://{self._bucket}/{self._prefix}{key}"


def create_storage(settings: Settings) -> StorageBackend:
    """Factory to create the appropriate storage backend from settings.

    Args:
        settings: Application settings.

    Returns:
        Configured StorageBackend instance.

    Raises:
        ValueError: If storage_backend is not recognized.
    """
    backend = settings.storage_backend.lower()

    if backend == "local":
        logger.info("Using local filesystem storage")
        return LocalStorage(base_dir=settings.output_dir)

    if backend == "s3":
        if not settings.s3_bucket:
            raise ValueError("S3_BUCKET must be set when using S3 storage backend")
        logger.info("Using S3 storage: bucket=%s", settings.s3_bucket)
        return S3Storage(
            bucket=settings.s3_bucket,
            prefix=settings.s3_prefix,
            region=settings.s3_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )

    raise ValueError(f"Unknown storage backend: '{backend}'. Supported: 'local', 's3'")


def sync_to_storage(settings: Settings, result: object) -> None:
    """Sync pipeline output assets to the configured storage backend.

    No-op when the backend is 'local' since assets are already on disk.

    Args:
        settings: Application settings.
        result: PipelineResult containing product/asset data.
    """
    if settings.storage_backend == "local":
        return

    storage = create_storage(settings)
    output_base = Path(settings.output_dir)
    synced = 0
    for pr in result.products:  # type: ignore[attr-defined]
        for asset in pr.assets:
            asset_path = Path(asset.output_path)
            if asset_path.exists():
                try:
                    relative_key = str(asset_path.relative_to(output_base))
                except ValueError:
                    relative_key = asset_path.name
                storage.save(asset_path, relative_key)
                synced += 1
    logger.info("Storage sync complete: %d assets uploaded", synced)


def delete_from_storage(settings: Settings, campaign_slug: str, version: int) -> None:
    """Delete a campaign version's assets from the configured storage backend.

    No-op when the backend is 'local' since local deletion is handled separately.

    Args:
        settings: Application settings.
        campaign_slug: Slugified campaign name.
        version: Version number to delete.
    """
    if settings.storage_backend == "local":
        return

    storage = create_storage(settings)
    prefix = f"{campaign_slug}/v{version}/"
    deleted = storage.delete(prefix)
    logger.info("Deleted %d assets from storage for %s/v%d", deleted, campaign_slug, version)
