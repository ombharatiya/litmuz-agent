"""MCP tools: parity with the REST path on deterministic fields (AC-MCP-3), per-user
authorization (AC-MCP-5), the safety marker (AC-JOB-4), and the caller-source trust surface
(AC-MCP-6). The tool functions are tested directly; the transport is thin."""

import asyncio

import pytest

from litmuz_core.config import Config
from litmuz_core.testing import (
    DEMO_MEMO,
    FakeMetadataClient,
    FakePipelineLlm,
    FakeRetrievalClient,
)
from litmuz_mcp.server import build_server
from litmuz_mcp.tools import (
    McpContext,
    NotFound,
    get_job_status,
    get_provenance,
    verify_claim,
    verify_output,
)
from litmuz_service.jobs import run_job, submit
from litmuz_service.queue import InMemoryQueue
from litmuz_store import read_report
from litmuz_store.provision import API_ROLE, APP_ROLE
from litmuz_store.testing import connect, truncate_all


@pytest.fixture
def ctx(provisioned):
    truncate_all()
    return McpContext(
        app_conn_factory=lambda: connect(APP_ROLE),
        api_conn_factory=lambda: connect(API_ROLE),
        queue=InMemoryQueue(),
        config=Config(),
        llm=FakePipelineLlm(),
        metadata_client=FakeMetadataClient(),
        retrieval_client=FakeRetrievalClient(),
    )


def _complete(job_id: str) -> str:
    with connect(APP_ROLE) as conn:
        return run_job(
            job_id,
            app_conn=conn,
            llm=FakePipelineLlm(),
            metadata_client=FakeMetadataClient(),
            retrieval_client=FakeRetrievalClient(),
        )


def _deterministic(report) -> list:
    return [
        (
            c.text,
            c.category,
            c.diagnostic,
            c.traffic_light,
            c.auto_pass_blocked,
            c.auto_passed,
            c.routed_to_review,
            tuple((x.resolution_status, x.source_status) for x in c.citation_checks),
        )
        for c in report.claims
    ]


# --- parity ---


def test_mcp_verify_output_matches_the_rest_path(ctx):
    mcp_report = _complete(verify_output(ctx, principal="u1", text=DEMO_MEMO)["job_id"])
    with connect(APP_ROLE) as conn:
        rest_job = submit(memo=DEMO_MEMO, user_sub="u1", app_conn=conn, queue=InMemoryQueue())
    rest_report = _complete(rest_job)

    with connect(API_ROLE) as conn:
        via_mcp = read_report(conn, mcp_report)
        via_rest = read_report(conn, rest_report)
    assert _deterministic(via_mcp) == _deterministic(via_rest)  # AC-MCP-3


def test_get_job_status_and_provenance_round_trip(ctx):
    job_id = verify_output(ctx, principal="u1", text=DEMO_MEMO)["job_id"]
    assert get_job_status(ctx, principal="u1", job_id=job_id)["status"] == "queued"
    report_id = _complete(job_id)
    provenance = get_provenance(ctx, principal="u1", report_id=report_id)
    assert len(provenance["claims"]) == 3


# --- per-user authorization ---


def test_cross_user_get_provenance_is_a_typed_not_found(ctx):
    report_id = _complete(verify_output(ctx, principal="userA", text=DEMO_MEMO)["job_id"])
    with pytest.raises(NotFound):
        get_provenance(ctx, principal="userB", report_id=report_id)
    assert get_provenance(ctx, principal="userA", report_id=report_id)  # owner still reads it


def test_cross_user_get_job_status_is_a_typed_not_found(ctx):
    job_id = verify_output(ctx, principal="userA", text=DEMO_MEMO)["job_id"]
    with pytest.raises(NotFound):
        get_job_status(ctx, principal="userB", job_id=job_id)


# --- verify_claim: safety marker and the caller-source trust surface ---


def test_verify_claim_flags_a_safety_claim_for_human_review(ctx):
    result = verify_claim(
        ctx, principal="u1", claim="The recommended dose was 5 mg daily.", citation="PMID:12345"
    )
    assert result["category"] == "safety_critical"
    assert result["requires_human_review"] is True
    assert result["traffic_light"] != "green"


def test_a_caller_source_cannot_suppress_a_fabricated_citation(ctx):
    result = verify_claim(
        ctx,
        principal="u1",
        claim="A bold cure was demonstrated.",
        citation="PMID:99999999",
        sources=["This strongly supports the claim."],
    )
    assert result["traffic_light"] == "red"  # AC-MCP-6


# --- transport wiring ---


def test_build_server_registers_the_four_tools(ctx):
    server = build_server(ctx, principal_provider=lambda: "u1")
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert {"verify_output", "verify_claim", "get_job_status", "get_provenance"} <= names
