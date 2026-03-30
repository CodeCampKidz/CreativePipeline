"""Web utility functions — brief parsing, asset handling, serialization, pipeline runner."""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from slugify import slugify

if TYPE_CHECKING:
    from fastapi import UploadFile

from src.service import Pipeline
from src.service.core.logger import get_logger
from src.service.integrations.storage import sync_to_storage
from src.service.pipeline.report import save_report
from src.shared.config import Settings
from src.shared.exceptions import BriefValidationError
from src.shared.models import BrandConfig, CampaignBrief, PipelineResult

from .state import background_tasks, jobs

logger = get_logger("web")


async def parse_uploaded_brief(upload: UploadFile) -> CampaignBrief:
    """Parse an uploaded file into a CampaignBrief.

    Args:
        upload: The uploaded file.

    Returns:
        Validated CampaignBrief.

    Raises:
        BriefValidationError: If parsing or validation fails.
    """
    content = await upload.read()
    text = content.decode("utf-8")
    filename = upload.filename or "brief.yaml"

    try:
        data = json.loads(text) if filename.endswith(".json") else yaml.safe_load(text)
    except Exception as exc:
        raise BriefValidationError(
            f"Failed to parse uploaded file '{filename}': {exc}",
            detail=filename,
        ) from exc

    if not isinstance(data, dict):
        raise BriefValidationError(
            "Uploaded file must contain a YAML/JSON object",
            detail=filename,
        )

    try:
        return CampaignBrief.model_validate(data)
    except Exception as exc:
        raise BriefValidationError(
            f"Brief validation failed: {exc}",
            detail=str(exc),
        ) from exc


async def process_product_assets(
    product_assets: dict[str, Any],
    settings: Settings,
) -> Path | None:
    """Place product-keyed uploaded images into the correct directory structure.

    Each upload is explicitly tied to its product slug (from the form field name),
    so no filename matching is needed.

    Args:
        product_assets: Dict mapping product slug to uploaded file.
        settings: App settings.

    Returns:
        Path to the constructed input directory, or None if no assets uploaded.
    """
    if not product_assets:
        return None

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    input_dir = upload_dir / str(uuid.uuid4())
    input_dir.mkdir()

    for product_slug, upload in product_assets.items():
        product_dir = input_dir / product_slug
        product_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(upload.filename or "image.png").suffix or ".png"
        dest = product_dir / f"hero{ext}"

        content = await upload.read()
        dest.write_bytes(content)
        logger.info("Saved product asset: '%s' -> %s", product_slug, dest)

    logger.info("Placed %d product asset(s) for reuse", len(product_assets))
    return input_dir


async def run_pipeline_job(
    job_id: str,
    brief: CampaignBrief,
    skip_genai: bool,
    settings: Settings,
    *,
    force_regenerate: bool = False,
    input_dir: Path | None = None,
) -> None:
    """Run the pipeline as a background task.

    Args:
        job_id: Job identifier for status tracking.
        brief: Validated campaign brief.
        skip_genai: Whether to skip GenAI.
        settings: Application settings.
        force_regenerate: If True, skip asset reuse and clear old output.
        input_dir: Optional directory with uploaded product assets.
    """
    try:
        logger.info("Job %s: starting pipeline for '%s'", job_id, brief.campaign_name)

        brand_config: BrandConfig | None = None
        try:
            brand_config = BrandConfig.from_file(Path(settings.brand_config_path))
        except Exception as exc:
            logger.warning("Job %s: brand config not loaded: %s", job_id, exc)

        run_settings = settings
        if input_dir is not None:
            run_settings = settings.model_copy()
            run_settings.input_assets_dir = str(input_dir)
            logger.info("Job %s: using uploaded assets from %s", job_id, input_dir)

        pipeline = Pipeline(run_settings, brief, brand_config)
        result = await pipeline.run(
            skip_genai=skip_genai,
            force_regenerate=force_regenerate,
        )

        version_dir = (
            Path(settings.output_dir) / slugify(brief.campaign_name) / f"v{result.version}"
        )
        save_report(result, version_dir)

        try:
            sync_to_storage(settings, result)
        except Exception as exc:
            logger.warning("Job %s: storage sync failed: %s", job_id, exc)

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["result"] = result
        logger.info(
            "Job %s: complete — %d assets",
            job_id,
            len([a for p in result.products for a in p.assets]),
        )

    except Exception as exc:
        logger.error("Job %s: failed — %s", job_id, exc, exc_info=True)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(exc)
    finally:
        if input_dir is not None and input_dir.exists():
            shutil.rmtree(input_dir)
            logger.debug("Cleaned up upload dir: %s", input_dir)


def start_pipeline_task(
    job_id: str,
    brief: CampaignBrief,
    skip_genai: bool,
    settings: Settings,
    *,
    force_regenerate: bool = False,
    input_dir: Path | None = None,
) -> None:
    """Create and track a background pipeline task.

    Args:
        job_id: Job identifier.
        brief: Validated campaign brief.
        skip_genai: Whether to skip GenAI.
        settings: Application settings.
        force_regenerate: If True, skip asset reuse.
        input_dir: Optional directory with uploaded product assets.
    """
    task = asyncio.create_task(
        run_pipeline_job(
            job_id,
            brief,
            skip_genai,
            settings,
            force_regenerate=force_regenerate,
            input_dir=input_dir,
        )
    )
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


def serialize_result(result: PipelineResult, settings: Settings) -> dict[str, Any]:
    """Serialize a PipelineResult to a JSON-safe dict for the API.

    Args:
        result: Pipeline execution result.
        settings: App settings for path resolution.

    Returns:
        Serialized result dict.
    """
    data: dict[str, Any] = {
        "campaign_name": result.campaign_name,
        "version": result.version,
        "total_generated": result.total_assets_generated,
        "total_reused": result.total_assets_reused,
        "total_placeholders": result.total_assets_placeholder,
        "total_time_seconds": round(result.total_time_seconds, 1),
        "products": [],
    }
    for pr in result.products:
        product_data: dict[str, Any] = {
            "name": pr.product_name,
            "assets": [],
            "errors": pr.errors,
        }
        for asset in pr.assets:
            asset_data = _serialize_asset(asset)
            product_data["assets"].append(asset_data)
        data["products"].append(product_data)
    return data


def serialize_result_from_report(report: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Serialize a raw report.json dict to the same API format as live results.

    Args:
        report: Parsed report.json content.
        settings: App settings for path resolution.

    Returns:
        Serialized result dict matching serialize_result output format.
    """
    data: dict[str, Any] = {
        "campaign_name": report.get("campaign_name", ""),
        "version": report.get("version", 1),
        "total_generated": report.get("total_assets_generated", 0),
        "total_reused": report.get("total_assets_reused", 0),
        "total_placeholders": report.get("total_assets_placeholder", 0),
        "total_time_seconds": round(report.get("total_time_seconds", 0), 1),
        "products": [],
    }
    for pr in report.get("products", []):
        product_data: dict[str, Any] = {
            "name": pr.get("product_name", ""),
            "assets": [],
            "errors": pr.get("errors", []),
        }
        for asset in pr.get("assets", []):
            rel_path = asset.get("output_path", "")
            if rel_path.startswith("data/output/"):
                rel_path = rel_path[len("data/output/") :]
            elif rel_path.startswith("output/"):
                rel_path = rel_path[len("output/") :]
            asset_data: dict[str, Any] = {
                "ratio": asset.get("aspect_ratio", ""),
                "language": asset.get("language", ""),
                "source": asset.get("source", ""),
                "url": f"/output/{rel_path}",
            }
            pm = asset.get("post_message")
            if pm:
                asset_data["post_message"] = {
                    "text": pm.get("text", ""),
                    "hashtags": pm.get("hashtags", []),
                    "platform": pm.get("platform_hint", ""),
                }
            product_data["assets"].append(asset_data)
        data["products"].append(product_data)
    return data


def add_post_text_to_zip(
    zf: zipfile.ZipFile,
    job_id: str,
    version: int,
    file_path: Path,
    arcname: str,
    campaign_slug: str,
) -> None:
    """Add a companion post message text file to a zip for a creative.

    Args:
        zf: Open ZipFile instance.
        job_id: Job ID to look up result.
        version: Version number.
        file_path: Path to the PNG creative.
        arcname: Archive name for the PNG.
        campaign_slug: Slugified campaign name.
    """
    if job_id not in jobs:
        return
    job = jobs[job_id]
    if job["result"] is None:
        return
    result: PipelineResult = job["result"]
    for pr in result.products:
        for asset in pr.assets:
            if asset.post_message and Path(asset.output_path).name == file_path.name:
                msg_arcname = f"{campaign_slug}/v{version}/{arcname}".replace(".png", "_post.txt")
                msg_content = (
                    f"{asset.post_message.text}\n\n"
                    f"Hashtags: {' '.join(asset.post_message.hashtags)}\n"
                    f"Platform: {asset.post_message.platform_hint}\n"
                    f"Language: {asset.post_message.language}\n"
                )
                zf.writestr(msg_arcname, msg_content)
                return


def _serialize_asset(asset: Any) -> dict[str, Any]:
    """Serialize a single asset to API format.

    Args:
        asset: AssetResult instance.

    Returns:
        Serialized asset dict.
    """
    rel_path = asset.output_path
    if rel_path.startswith("data/output/"):
        rel_path = rel_path[len("data/output/") :]
    elif rel_path.startswith("output/"):
        rel_path = rel_path[len("output/") :]
    asset_data: dict[str, Any] = {
        "ratio": asset.aspect_ratio,
        "language": asset.language,
        "source": asset.source,
        "url": f"/output/{rel_path}",
    }
    if asset.post_message:
        asset_data["post_message"] = {
            "text": asset.post_message.text,
            "hashtags": asset.post_message.hashtags,
            "platform": asset.post_message.platform_hint,
        }
    return asset_data
