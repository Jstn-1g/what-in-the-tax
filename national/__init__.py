"""Deterministic Canada-wide geography and governing-body ingestion.

The core registry exports no model client and performs no network requests at
import or build time. Official source payloads are acquired by a separate,
explicit transport step, content-addressed, and then parsed offline. The
optional local subscription worker is isolated in ``national.subscription_worker``
and is never imported by this package surface.
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
