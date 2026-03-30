"""Tests for storage abstraction — local and S3 backends."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.service.integrations.storage import LocalStorage, S3Storage, create_storage
from src.shared.config import Settings


class TestLocalStorage:
    """Tests for local filesystem storage."""

    def test_save_copies_file(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path / "output"))
        src_file = tmp_path / "source.png"
        Image.new("RGB", (10, 10)).save(str(src_file))

        result = storage.save(src_file, "campaign/product/creative.png")
        assert Path(result).exists()
        assert "creative.png" in result

    def test_list_assets(self, tmp_path: Path) -> None:
        output = tmp_path / "output" / "campaign"
        output.mkdir(parents=True)
        (output / "file1.png").write_text("img1")
        (output / "file2.png").write_text("img2")

        storage = LocalStorage(base_dir=str(tmp_path / "output"))
        assets = storage.list_assets("campaign")
        assert len(assets) == 2

    def test_list_assets_empty_dir(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path / "output"))
        assets = storage.list_assets("nonexistent")
        assert assets == []

    def test_get_uri(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path / "output"))
        uri = storage.get_uri("campaign/file.png")
        assert uri.endswith("campaign/file.png")

    def test_save_creates_nested_dirs(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path / "output"))
        src_file = tmp_path / "source.png"
        Image.new("RGB", (10, 10)).save(str(src_file))

        result = storage.save(src_file, "deep/nested/path/creative.png")
        assert Path(result).exists()


class TestS3Storage:
    """Tests for S3 storage with mocked boto3."""

    @patch("boto3.client")
    def test_s3_save_calls_upload(self, mock_client_fn: MagicMock, tmp_path: Path) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        storage = S3Storage(bucket="test-bucket", prefix="campaigns/", region="us-east-1")

        src_file = tmp_path / "image.png"
        Image.new("RGB", (10, 10)).save(str(src_file))

        uri = storage.save(src_file, "campaign/product/creative.png")
        assert uri == "s3://test-bucket/campaigns/campaign/product/creative.png"
        mock_client.upload_file.assert_called_once()

    @patch("boto3.client")
    def test_s3_list_assets(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "campaigns/campaign/file1.png"},
                {"Key": "campaigns/campaign/file2.png"},
            ]
        }
        mock_client_fn.return_value = mock_client

        storage = S3Storage(bucket="test-bucket", prefix="campaigns/")
        assets = storage.list_assets("campaign/")
        assert len(assets) == 2

    @patch("boto3.client")
    def test_s3_get_uri(self, mock_client_fn: MagicMock) -> None:
        mock_client_fn.return_value = MagicMock()
        storage = S3Storage(bucket="my-bucket", prefix="data/")
        assert storage.get_uri("file.png") == "s3://my-bucket/data/file.png"


class TestCreateStorage:
    """Tests for storage factory function."""

    def test_creates_local_by_default(self, tmp_path: Path) -> None:
        settings = Settings(output_dir=str(tmp_path), storage_backend="local")
        storage = create_storage(settings)
        assert isinstance(storage, LocalStorage)

    @patch("boto3.client")
    def test_creates_s3(self, mock_client_fn: MagicMock) -> None:
        mock_client_fn.return_value = MagicMock()
        settings = Settings(storage_backend="s3", s3_bucket="test-bucket")
        storage = create_storage(settings)
        assert isinstance(storage, S3Storage)

    def test_s3_without_bucket_raises(self) -> None:
        settings = Settings(storage_backend="s3", s3_bucket="")
        with pytest.raises(ValueError, match="S3_BUCKET must be set"):
            create_storage(settings)

    def test_unknown_backend_raises(self) -> None:
        settings = Settings(storage_backend="azure")
        with pytest.raises(ValueError, match="Unknown storage backend"):
            create_storage(settings)
