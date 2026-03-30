"""Shared in-memory state for job tracking."""

from __future__ import annotations

import asyncio
from typing import Any

# In-memory job tracking (sufficient for PoC single-instance server)
jobs: dict[str, dict[str, Any]] = {}
background_tasks: set[asyncio.Task[None]] = set()
