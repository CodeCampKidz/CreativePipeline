"""Job-scoped API routes — status, versions, regenerate, download, delete."""

from __future__ import annotations

import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from slugify import slugify

from src.service.core.logger import get_logger
from src.service.integrations.storage import delete_from_storage
from src.shared.config import Settings, get_settings
from src.shared.models import PipelineResult

from ..state import jobs
from ..utils import (
    add_post_text_to_zip,
    serialize_result,
    start_pipeline_task,
)

logger = get_logger("web")
router = APIRouter(prefix="/api", tags=["Jobs"])


@router.get("/jobs")
async def list_jobs() -> JSONResponse:
    """List all jobs and their statuses."""
    return JSONResponse({job_id: {"status": job["status"]} for job_id, job in jobs.items()})


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Get the status and results of a generation job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    job = jobs[job_id]
    response: dict[str, Any] = {"job_id": job_id, "status": job["status"]}

    if job["status"] == "complete" and job["result"] is not None:
        result: PipelineResult = job["result"]
        response["result"] = serialize_result(result, settings)
    elif job["status"] == "failed":
        response["error"] = job["error"]

    return JSONResponse(response)


@router.get("/jobs/{job_id}/versions")
async def list_versions(
    job_id: str,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """List all versions for a job's campaign."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    job = jobs[job_id]
    brief = job["brief"]
    campaign_slug = slugify(brief.campaign_name)
    campaign_dir = Path(settings.output_dir) / campaign_slug

    versions: list[dict[str, Any]] = []
    if campaign_dir.exists():
        for d in sorted(campaign_dir.iterdir()):
            if d.is_dir() and d.name.startswith("v") and d.name[1:].isdigit():
                v_num = int(d.name[1:])
                report_path = d / "report.json"
                versions.append(
                    {
                        "version": v_num,
                        "path": d.name,
                        "has_report": report_path.exists(),
                    }
                )

    return JSONResponse({"campaign": campaign_slug, "versions": versions})


@router.get("/jobs/{job_id}/versions/{version}/download")
async def download_version(
    job_id: str,
    version: int,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """Download a specific version's creatives as a zip archive."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    brief = jobs[job_id]["brief"]
    campaign_slug = slugify(brief.campaign_name)
    version_dir = Path(settings.output_dir) / campaign_slug / f"v{version}"

    if not version_dir.exists():
        raise HTTPException(status_code=404, detail=f"Version v{version} not found")

    zip_path = Path(settings.output_dir) / f"{campaign_slug}-v{version}.zip"

    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in version_dir.rglob("*"):
            if file_path.is_file():
                arcname = str(file_path.relative_to(version_dir))
                zf.write(str(file_path), f"{campaign_slug}/v{version}/{arcname}")

                if file_path.suffix == ".png":
                    add_post_text_to_zip(zf, job_id, version, file_path, arcname, campaign_slug)

    logger.info("Created download zip: %s", zip_path)
    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename=f"{campaign_slug}-v{version}-creatives.zip",
    )


@router.delete("/jobs/{job_id}/versions/{version}")
async def delete_version(
    job_id: str,
    version: int,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Delete a specific version's output."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    brief = jobs[job_id]["brief"]
    campaign_slug = slugify(brief.campaign_name)
    version_dir = Path(settings.output_dir) / campaign_slug / f"v{version}"

    if not version_dir.exists():
        raise HTTPException(status_code=404, detail=f"Version v{version} not found")

    shutil.rmtree(version_dir)
    delete_from_storage(settings, campaign_slug, version)
    logger.info("Deleted version v%d for campaign '%s'", version, campaign_slug)
    return JSONResponse({"deleted": f"v{version}", "campaign": campaign_slug})


@router.post("/jobs/{job_id}/regenerate")
async def regenerate_job(
    job_id: str,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Create a new version by re-running the pipeline with fresh AI content."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    old_job = jobs[job_id]
    brief = old_job["brief"]

    new_job_id = str(uuid.uuid4())[:8]
    jobs[new_job_id] = {
        "status": "running",
        "brief": brief,
        "result": None,
        "error": None,
    }

    start_pipeline_task(new_job_id, brief, False, settings, force_regenerate=True)

    logger.info("Regenerating job %s as new job %s (new version)", job_id, new_job_id)
    return JSONResponse(
        {
            "job_id": new_job_id,
            "status": "running",
            "status_url": f"/api/jobs/{new_job_id}",
            "original_job_id": job_id,
        }
    )
