"""Campaign-scoped API routes — browse, download, delete campaigns from disk."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from src.service.core.logger import get_logger
from src.service.integrations.storage import delete_from_storage
from src.shared.config import Settings, get_settings

from ..utils import serialize_result_from_report

logger = get_logger("web")
router = APIRouter(prefix="/api/campaigns")


@router.get("")
async def list_campaigns(settings: Settings = Depends(get_settings)) -> JSONResponse:
    """List all campaigns on disk with their versions."""
    output_path = Path(settings.output_dir)
    campaigns: list[dict[str, Any]] = []

    if not output_path.exists():
        return JSONResponse({"campaigns": []})

    for campaign_dir in sorted(output_path.iterdir()):
        if not campaign_dir.is_dir() or campaign_dir.name.startswith("."):
            continue

        versions: list[dict[str, Any]] = []
        campaign_name = campaign_dir.name

        for v_dir in sorted(campaign_dir.iterdir()):
            if not (v_dir.is_dir() and v_dir.name.startswith("v") and v_dir.name[1:].isdigit()):
                continue
            v_num = int(v_dir.name[1:])
            report_path = v_dir / "report.json"

            v_info: dict[str, Any] = {"version": v_num}
            if report_path.exists():
                try:
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    v_info["campaign_name"] = report.get("campaign_name", campaign_name)
                    v_info["total_assets"] = (
                        report.get("total_assets_generated", 0)
                        + report.get("total_assets_reused", 0)
                        + report.get("total_assets_placeholder", 0)
                    )
                    v_info["total_time_seconds"] = report.get("total_time_seconds", 0)
                except Exception:
                    pass
            versions.append(v_info)

        if versions:
            display_name = versions[0].get("campaign_name", campaign_name)
            campaigns.append(
                {
                    "slug": campaign_name,
                    "name": display_name,
                    "versions": len(versions),
                    "latest_version": versions[-1]["version"],
                    "version_list": versions,
                }
            )

    return JSONResponse({"campaigns": campaigns})


@router.get("/{campaign_slug}")
async def get_campaign(
    campaign_slug: str,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Get details for a specific campaign including all versions."""
    campaign_dir = Path(settings.output_dir) / campaign_slug

    if not campaign_dir.exists():
        raise HTTPException(status_code=404, detail=f"Campaign '{campaign_slug}' not found")

    versions: list[dict[str, Any]] = []
    for v_dir in sorted(campaign_dir.iterdir()):
        if not (v_dir.is_dir() and v_dir.name.startswith("v") and v_dir.name[1:].isdigit()):
            continue

        v_num = int(v_dir.name[1:])
        report_path = v_dir / "report.json"
        v_data: dict[str, Any] = {"version": v_num, "has_report": report_path.exists()}

        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                v_data["result"] = serialize_result_from_report(report, settings)
            except Exception as exc:
                logger.warning("Failed to load report for %s/v%d: %s", campaign_slug, v_num, exc)

        versions.append(v_data)

    if not versions:
        raise HTTPException(status_code=404, detail=f"No versions found for '{campaign_slug}'")

    return JSONResponse(
        {
            "slug": campaign_slug,
            "name": versions[0].get("result", {}).get("campaign_name", campaign_slug),
            "versions": versions,
        }
    )


@router.get("/{campaign_slug}/versions/{version}")
async def get_campaign_version(
    campaign_slug: str,
    version: int,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Get a specific version's full results from disk."""
    report_path = Path(settings.output_dir) / campaign_slug / f"v{version}" / "report.json"

    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Version v{version} not found for campaign '{campaign_slug}'",
        )

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return JSONResponse(
            {
                "slug": campaign_slug,
                "version": version,
                "result": serialize_result_from_report(report, settings),
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load report: {exc}") from exc


@router.delete("/{campaign_slug}/versions/{version}")
async def delete_campaign_version(
    campaign_slug: str,
    version: int,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Delete a specific version from a campaign."""
    version_dir = Path(settings.output_dir) / campaign_slug / f"v{version}"

    if not version_dir.exists():
        raise HTTPException(status_code=404, detail=f"Version v{version} not found")

    shutil.rmtree(version_dir)
    delete_from_storage(settings, campaign_slug, version)
    logger.info("Deleted %s/v%d", campaign_slug, version)
    return JSONResponse({"deleted": f"v{version}", "campaign": campaign_slug})


@router.get("/{campaign_slug}/versions/{version}/download")
async def download_campaign_version(
    campaign_slug: str,
    version: int,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """Download a specific version as a zip archive."""
    version_dir = Path(settings.output_dir) / campaign_slug / f"v{version}"

    if not version_dir.exists():
        raise HTTPException(status_code=404, detail=f"Version v{version} not found")

    zip_path = Path(settings.output_dir) / f"{campaign_slug}-v{version}.zip"
    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in version_dir.rglob("*"):
            if file_path.is_file():
                arcname = str(file_path.relative_to(version_dir))
                zf.write(str(file_path), f"{campaign_slug}/v{version}/{arcname}")

    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename=f"{campaign_slug}-v{version}-creatives.zip",
    )
