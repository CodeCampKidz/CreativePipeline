"""Compliance package — brand and legal content checks."""

from src.service.compliance.brand_checker import check_brand_compliance
from src.service.compliance.legal_checker import check_legal_content

__all__ = [
    "check_brand_compliance",
    "check_legal_content",
]
