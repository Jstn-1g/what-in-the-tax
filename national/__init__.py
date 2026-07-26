"""Deterministic Canada-wide geography and governing-body ingestion.

This package deliberately contains no model client and performs no network
requests at import or build time. Official source payloads are acquired by a
separate, explicit transport step, content-addressed, and then parsed offline.
"""

from .models import (
    GoverningBodyRecord,
    GeographyRecord,
    ProvenanceRef,
    SourceSnapshot,
)
from .registry import NationalRegistryBuilder, RegistryError

__all__ = [
    "GoverningBodyRecord",
    "GeographyRecord",
    "NationalRegistryBuilder",
    "ProvenanceRef",
    "RegistryError",
    "SourceSnapshot",
]
