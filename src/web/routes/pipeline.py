"""Pipeline routes — validate briefs and submit generation requests."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from src.service.core.logger import get_logger
from src.shared.config import Settings, get_settings
from src.shared.exceptions import BriefValidationError

from ..state import jobs
from ..utils import (
    parse_uploaded_brief,
    process_product_assets,
    start_pipeline_task,
)

logger = get_logger("web")
router = APIRouter(prefix="/api", tags=["Pipeline"])


@router.post("/validate")
async def validate_brief(
    brief_file: UploadFile = File(..., description="Campaign brief YAML or JSON file"),
) -> JSONResponse:
    """Validate an uploaded campaign brief without generating assets."""
    logger.info("Validating brief: %s", brief_file.filename)
    try:
        brief = await parse_uploaded_brief(brief_file)
        return JSONResponse(
            {
                "valid": True,
                "campaign_name": brief.campaign_name,
                "products": [p.name for p in brief.products],
                "target_region": brief.target_region,
                "target_audience": brief.target_audience,
                "campaign_message": brief.campaign_message,
                "languages": brief.languages,
                "aspect_ratios": [r.value for r in brief.aspect_ratios],
                "total_creatives": (
                    len(brief.products) * len(brief.aspect_ratios) * len(brief.languages)
                ),
            }
        )
    except BriefValidationError as exc:
        logger.warning("Brief validation failed: %s", exc)
        return JSONResponse({"valid": False, "error": str(exc)}, status_code=400)


@router.post("/generate")
async def generate_creatives(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Upload a brief and optional per-product images, then start generation."""
    form = await request.form()

    brief_file = form.get("brief_file")
    if brief_file is None or not hasattr(brief_file, "read"):
        raise HTTPException(status_code=400, detail="brief_file is required")

    skip_genai = str(form.get("skip_genai", "false")).lower() == "true"

    try:
        brief = await parse_uploaded_brief(brief_file)  # type: ignore[arg-type]
    except BriefValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    product_assets: dict[str, Any] = {}
    for key in form:
        value = form[key]
        if key.startswith("product_asset_") and hasattr(value, "read"):
            product_slug = key[len("product_asset_"):]
            if hasattr(value, "size") and value.size and value.size > 0:
                product_assets[product_slug] = value

    logger.info(
        "Generate request: brief=%s, product_assets=%s, skip_genai=%s",
        getattr(brief_file, "filename", "unknown"),
        list(product_assets.keys()) or "none",
        skip_genai,
    )

    input_dir = await process_product_assets(product_assets, settings)

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "running",
        "brief": brief,
        "result": None,
        "error": None,
    }

    start_pipeline_task(job_id, brief, skip_genai, settings, input_dir=input_dir)

    return JSONResponse(
        {
            "job_id": job_id,
            "status": "running",
            "status_url": f"/api/jobs/{job_id}",
        }
    )
