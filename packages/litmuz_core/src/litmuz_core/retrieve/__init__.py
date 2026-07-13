"""Evidence retrieval stage (FR-3). Decides provenance and returns ranked passages."""

from .clients import (
    CitedSource,
    NcbiPmcClient,
    RetrievalClient,
    RetrievalTransient,
)
from .retriever import RetrievalError, build_query, retrieve_for_claim

__all__ = [
    "CitedSource",
    "NcbiPmcClient",
    "RetrievalClient",
    "RetrievalTransient",
    "RetrievalError",
    "build_query",
    "retrieve_for_claim",
]
