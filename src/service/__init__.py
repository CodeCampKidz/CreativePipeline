"""Service layer — pipeline engine, integrations, and compliance.

This package contains all business logic for creative generation.
On microservice split, this becomes a standalone service.
"""

from src.service.pipeline.orchestrator import Pipeline

__all__ = ["Pipeline"]
