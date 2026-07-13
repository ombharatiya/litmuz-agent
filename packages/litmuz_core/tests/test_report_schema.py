"""AC-REPORT-2: a report validates against the published JSON schema, and a report with a
missing required field fails validation. The schema is exported from the pydantic model."""

import jsonschema
import pytest

from litmuz_core.schemas import Report, export_report_json_schema


def _valid_report_dict() -> dict:
    report = Report(id="r1", job_id="j1", memo_hash="deadbeef", created_at="2026-07-03T00:00:00Z")
    return report.model_dump(mode="json")


def test_valid_report_validates_against_the_published_schema():
    jsonschema.validate(instance=_valid_report_dict(), schema=export_report_json_schema())


def test_missing_required_field_fails_validation():
    schema = export_report_json_schema()
    incomplete = _valid_report_dict()
    del incomplete["id"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=incomplete, schema=schema)
