"""Shared test fixtures. The FakeClient resolves from a JSON corpus so unit tests
never touch the network (AC-CITE unit tests) and the corpus is data-driven."""

from __future__ import annotations

import json
import pathlib

import pytest

from litmuz_core.cite.clients import Resolution, ResolutionOutcome, SourceRecord, TransientError
from litmuz_core.config import Config, SourceStatus

FIXTURES = pathlib.Path(__file__).resolve().parents[3] / "fixtures"


def _to_resolution(spec: dict) -> Resolution | str:
    outcome = spec["outcome"]
    if outcome == "transient":
        return "transient"
    if outcome == "absent":
        return Resolution(ResolutionOutcome.ABSENT, resolver_path="fixture")
    if outcome == "unresolved":
        return Resolution(ResolutionOutcome.UNRESOLVED, resolver_path="fixture")
    record = SourceRecord(
        identifier=spec["key"],
        title=spec.get("title"),
        surnames=tuple(spec.get("surnames", [])),
        epub_year=spec.get("epub_year"),
        print_year=spec.get("print_year"),
        source_status=SourceStatus(spec.get("source_status", "active")),
    )
    return Resolution(ResolutionOutcome.FOUND, record, resolver_path="fixture")


def load_citation_table() -> dict[str, Resolution | str]:
    data = json.loads((FIXTURES / "citations" / "records.json").read_text())
    return {r["key"]: _to_resolution(r) for r in data["records"]}


class FakeClient:
    """In-memory MetadataClient. Unknown ids are ABSENT (fabricated) by default."""

    def __init__(self, table: dict[str, Resolution | str] | None = None) -> None:
        self.table = table if table is not None else load_citation_table()
        self.calls: list[str] = []

    def resolve(self, cited_id) -> Resolution:
        key = f"{cited_id.id_type.value}:{cited_id.value}"
        self.calls.append(key)
        entry = self.table.get(key)
        if entry is None:
            return Resolution(ResolutionOutcome.ABSENT, resolver_path="fixture-default")
        if entry == "transient":
            raise TransientError("fixture transient")
        return entry


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def config() -> Config:
    return Config()
