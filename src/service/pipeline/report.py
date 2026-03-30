"""Pipeline report generation — JSON summary of all results."""

from __future__ import annotations

import json
from pathlib import Path

from src.service.core.logger import get_logger
from src.shared.models import PipelineResult

__all__ = ["save_report"]

logger = get_logger("report")


def save_report(result: PipelineResult, output_dir: Path) -> Path:
    """Save pipeline results as a formatted JSON report.

    Args:
        result: Complete pipeline execution result.
        output_dir: Directory to save the report file.

    Returns:
        Path to the saved report.json file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"

    report_data = result.model_dump(mode="json")

    try:
        report_path.write_text(
            json.dumps(report_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Report saved to %s", report_path)
    except OSError as exc:
        logger.error("Failed to save report: %s", exc)
        raise

    return report_path
