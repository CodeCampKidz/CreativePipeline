"""Tests for FastAPI web interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from src.web.app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a test client with output directed to tmp_path."""
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_brief_bytes() -> bytes:
    """Valid campaign brief as JSON bytes for upload."""
    brief = {
        "campaign_name": "Test Campaign",
        "products": [
            {"name": "Product A", "description": "A test product"},
            {"name": "Product B", "description": "Another product"},
        ],
        "target_region": "US",
        "target_audience": "Test audience",
        "campaign_message": "Test message",
        "languages": ["en"],
        "aspect_ratios": ["1:1"],
    }
    return json.dumps(brief).encode()


@pytest.fixture
def invalid_brief_bytes() -> bytes:
    """Invalid campaign brief (only one product) as JSON bytes."""
    brief = {
        "campaign_name": "Bad Campaign",
        "products": [{"name": "Only One", "description": "Single product"}],
        "target_region": "US",
        "target_audience": "All",
        "campaign_message": "Buy now",
    }
    return json.dumps(brief).encode()


class TestWebHealth:
    """Health and basic route tests."""

    def test_health_endpoint(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_home_page_renders(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Creative Automation Pipeline" in resp.text
        assert "Upload Campaign Brief" in resp.text


class TestWebValidate:
    """Brief validation endpoint tests."""

    def test_validate_valid_brief(self, client: TestClient, sample_brief_bytes: bytes) -> None:
        resp = client.post(
            "/api/validate",
            files={"brief_file": ("brief.json", sample_brief_bytes, "application/json")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["campaign_name"] == "Test Campaign"
        assert len(data["products"]) == 2
        assert data["total_creatives"] == 2  # 2 products * 1 ratio * 1 lang

    def test_validate_yaml_brief(self, client: TestClient) -> None:
        brief = {
            "campaign_name": "YAML Test",
            "products": [
                {"name": "A", "description": "a"},
                {"name": "B", "description": "b"},
            ],
            "target_region": "US",
            "target_audience": "All",
            "campaign_message": "Hello",
        }
        yaml_bytes = yaml.dump(brief).encode()
        resp = client.post(
            "/api/validate",
            files={"brief_file": ("brief.yaml", yaml_bytes, "application/x-yaml")},
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_validate_invalid_brief(self, client: TestClient, invalid_brief_bytes: bytes) -> None:
        resp = client.post(
            "/api/validate",
            files={"brief_file": ("bad.json", invalid_brief_bytes, "application/json")},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["valid"] is False
        assert "error" in data


class TestWebGenerate:
    """Creative generation endpoint tests."""

    def test_generate_starts_job(self, client: TestClient, sample_brief_bytes: bytes) -> None:
        resp = client.post(
            "/api/generate",
            files={"brief_file": ("brief.json", sample_brief_bytes, "application/json")},
            data={"skip_genai": "true"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "running"
        assert "status_url" in data

    def test_generate_invalid_brief_returns_400(
        self, client: TestClient, invalid_brief_bytes: bytes
    ) -> None:
        resp = client.post(
            "/api/generate",
            files={"brief_file": ("bad.json", invalid_brief_bytes, "application/json")},
            data={"skip_genai": "true"},
        )
        assert resp.status_code == 400

    def test_job_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/jobs/nonexistent")
        assert resp.status_code == 404

    def test_list_jobs(self, client: TestClient) -> None:
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)


class TestAssetUpload:
    """Tests for per-product image upload (two-step form)."""

    def test_generate_with_product_asset(
        self, client: TestClient, sample_brief_bytes: bytes
    ) -> None:
        """Upload an image for a specific product using product_asset_<slug> field."""
        import io

        from PIL import Image

        img = Image.new("RGB", (100, 100), color=(0, 100, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        resp = client.post(
            "/api/generate",
            files=[
                ("brief_file", ("brief.json", sample_brief_bytes, "application/json")),
                ("product_asset_product-a", ("hero.png", buf.getvalue(), "image/png")),
            ],
            data={"skip_genai": "true"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "running"

    def test_generate_with_multiple_product_assets(
        self, client: TestClient, sample_brief_bytes: bytes
    ) -> None:
        """Upload images for both products."""
        import io

        from PIL import Image

        img1 = Image.new("RGB", (100, 100), color=(0, 100, 200))
        buf1 = io.BytesIO()
        img1.save(buf1, format="PNG")

        img2 = Image.new("RGB", (100, 100), color=(200, 0, 100))
        buf2 = io.BytesIO()
        img2.save(buf2, format="PNG")

        resp = client.post(
            "/api/generate",
            files=[
                ("brief_file", ("brief.json", sample_brief_bytes, "application/json")),
                ("product_asset_product-a", ("hero.png", buf1.getvalue(), "image/png")),
                ("product_asset_product-b", ("hero.png", buf2.getvalue(), "image/png")),
            ],
            data={"skip_genai": "true"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_generate_without_assets(self, client: TestClient, sample_brief_bytes: bytes) -> None:
        """Generate with no product assets — all images AI generated."""
        resp = client.post(
            "/api/generate",
            files={"brief_file": ("brief.json", sample_brief_bytes, "application/json")},
            data={"skip_genai": "true"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"


class TestCampaignBrowser:
    """Campaign browsing endpoint tests (disk-based, no job required)."""

    def test_list_campaigns_empty(self, client: TestClient) -> None:
        resp = client.get("/api/campaigns")
        assert resp.status_code == 200
        data = resp.json()
        assert "campaigns" in data
        assert isinstance(data["campaigns"], list)

    def test_campaign_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/campaigns/nonexistent-campaign")
        assert resp.status_code == 404

    def test_campaign_version_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/campaigns/nonexistent/versions/1")
        assert resp.status_code == 404

    def test_delete_campaign_version_not_found(self, client: TestClient) -> None:
        resp = client.delete("/api/campaigns/nonexistent/versions/1")
        assert resp.status_code == 404

    def test_download_campaign_version_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/campaigns/nonexistent/versions/1/download")
        assert resp.status_code == 404
