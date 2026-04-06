"""Web route modules."""

from src.web.routes.campaigns import router as campaigns_router
from src.web.routes.jobs import router as jobs_router
from src.web.routes.pipeline import router as pipeline_router
from src.web.routes.ui import router as ui_router

__all__ = ["campaigns_router", "jobs_router", "pipeline_router", "ui_router"]
