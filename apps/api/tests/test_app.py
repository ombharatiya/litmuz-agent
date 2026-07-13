"""REST API: submit/poll/report end-to-end, typed error mapping, and the dark-ship and
enabled auth paths (Phase 4). A FastAPI TestClient over the real test database, with the
shared pipeline fakes driving the worker step."""

import pytest
from fastapi.testclient import TestClient

from litmuz_api.app import DEFAULT_PRINCIPAL, ApiContext, InvalidToken, create_app
from litmuz_core.config import Config
from litmuz_core.testing import (
    DEMO_MEMO,
    FakeMetadataClient,
    FakePipelineLlm,
    FakeRetrievalClient,
)
from litmuz_service.jobs import run_job
from litmuz_service.queue import InMemoryQueue
from litmuz_store.provision import API_ROLE, APP_ROLE
from litmuz_store.testing import connect, truncate_all


class FakeVerifier:
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def verify(self, token: str) -> str:
        if token in self.mapping:
            return self.mapping[token]
        raise InvalidToken("bad token")


def _complete(job_id: str) -> str:
    with connect(APP_ROLE) as conn:
        return run_job(
            job_id,
            app_conn=conn,
            llm=FakePipelineLlm(),
            metadata_client=FakeMetadataClient(),
            retrieval_client=FakeRetrievalClient(),
        )


@pytest.fixture
def make_client(provisioned):
    truncate_all()

    def _make(verifier=None):
        queue = InMemoryQueue()
        ctx = ApiContext(
            app_conn_factory=lambda: connect(APP_ROLE),
            api_conn_factory=lambda: connect(API_ROLE),
            queue=queue,
            verifier=verifier,
        )
        return TestClient(create_app(ctx)), queue

    return _make


# --- submit and validation (dark-ship) ---


def test_submit_returns_202_and_enqueues(make_client):
    client, queue = make_client()
    resp = client.post("/verifications", json={"text": DEMO_MEMO})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    assert queue.messages == [job_id]
    poll = client.get(f"/verifications/{job_id}")
    assert poll.status_code == 200
    body = poll.json()
    assert body["status"] == "queued"
    # The job detail carries the full memo (and title) so the studio can show a past session's
    # input beside its report rather than an empty composer.
    assert body["memo"] == DEMO_MEMO
    assert body["title"] == ""  # titled by the worker, which the dark-ship client does not run


def test_oversized_submission_is_413(make_client):
    client, queue = make_client()
    resp = client.post("/verifications", json={"text": "x" * (Config().max_input_bytes + 1)})
    assert resp.status_code == 413
    assert queue.messages == []


def test_empty_submission_is_400(make_client):
    client, _ = make_client()
    assert client.post("/verifications", json={"text": "   "}).status_code == 400


def test_missing_job_and_report_are_404(make_client):
    client, _ = make_client()
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.get(f"/verifications/{missing}").status_code == 404
    assert client.get(f"/reports/{missing}").status_code == 404


# --- full flow: submit, run, report, queue, review ---


def test_full_flow_submit_run_report_and_review(make_client):
    client, _ = make_client()
    job_id = client.post("/verifications", json={"text": DEMO_MEMO}).json()["job_id"]
    report_id = _complete(job_id)

    status = client.get(f"/verifications/{job_id}").json()
    assert status["status"] == "completed"
    assert status["report_id"] == report_id

    report = client.get(f"/reports/{report_id}")
    assert report.status_code == 200
    assert len(report.json()["claims"]) == 3

    export = client.get(f"/reports/{report_id}/export")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/markdown")
    assert export.text.startswith("# Litmuz report")

    queue = client.get("/queue").json()
    # Both the fabricated (red) claim and the dosing (safety-critical) claim are flagged.
    assert len(queue) == 2
    claim_id = next(c["claim_id"] for c in queue if "fabricated" in c["text"])

    review = client.post(
        f"/queue/{claim_id}/review",
        json={
            "action": "override_verdict",
            "new_verdict": {"label": "contradicted", "rationale": "human"},
        },
    )
    assert review.status_code == 204

    after = client.get(f"/reports/{report_id}").json()
    flagged = next(c for c in after["claims"] if c["id"] == claim_id)
    assert flagged["effective_verdict"]["label"] == "contradicted"
    # The reviewed claim's light is re-derived from the human's label (AC-REPORT-7 extended):
    # contradicted -> red, and the claim carries who decided it and how.
    assert flagged["effective_traffic_light"] == "red"
    assert flagged["reviewed"] is True
    assert flagged["review_action"] == "override_verdict"
    assert flagged["reviewed_by"] == DEFAULT_PRINCIPAL

    # A reviewed claim leaves the queue; the other flagged (safety) claim is still there.
    remaining = client.get("/queue").json()
    assert len(remaining) == 1
    assert remaining[0]["claim_id"] != claim_id

    # Accepting the other claim as-is also resolves it (no verdict change) and clears the queue.
    other_claim_id = remaining[0]["claim_id"]
    accept = client.post(f"/queue/{other_claim_id}/review", json={"action": "accept"})
    assert accept.status_code == 204
    assert client.get("/queue").json() == []
    accepted = next(
        c for c in client.get(f"/reports/{report_id}").json()["claims"] if c["id"] == other_claim_id
    )
    assert accepted["reviewed"] is True
    assert accepted["review_action"] == "accept"
    assert accepted["effective_traffic_light"] == accepted["traffic_light"]  # unchanged by accept


def test_override_verdict_requires_a_known_label_and_a_rationale(make_client):
    client, _ = make_client()
    job_id = client.post("/verifications", json={"text": DEMO_MEMO}).json()["job_id"]
    _complete(job_id)
    claim_id = client.get("/queue").json()[0]["claim_id"]

    bad_label = client.post(
        f"/queue/{claim_id}/review",
        json={"action": "override_verdict", "new_verdict": {"label": "maybe", "rationale": "x"}},
    )
    assert bad_label.status_code == 400

    no_rationale = client.post(
        f"/queue/{claim_id}/review",
        json={"action": "override_verdict", "new_verdict": {"label": "supported"}},
    )
    assert no_rationale.status_code == 400


def test_add_note_does_not_resolve_a_claim(make_client):
    client, _ = make_client()
    job_id = client.post("/verifications", json={"text": DEMO_MEMO}).json()["job_id"]
    _complete(job_id)
    before = len(client.get("/queue").json())
    claim_id = client.get("/queue").json()[0]["claim_id"]

    note = client.post(
        f"/queue/{claim_id}/review", json={"action": "add_note", "note": "checking further"}
    )
    assert note.status_code == 204
    assert len(client.get("/queue").json()) == before  # still there


def test_invalid_review_action_is_400(make_client):
    client, _ = make_client()
    job_id = client.post("/verifications", json={"text": DEMO_MEMO}).json()["job_id"]
    _complete(job_id)
    claim_id = client.get("/queue").json()[0]["claim_id"]
    assert client.post(f"/queue/{claim_id}/review", json={"action": "nonsense"}).status_code == 400


# --- studio session list ---


def test_me_jobs_returns_own_jobs_newest_first(make_client):
    client, _ = make_client(verifier=FakeVerifier({"tokA": "userA", "tokB": "userB"}))
    ha = {"Authorization": "Bearer tokA"}
    first = client.post("/verifications", json={"text": DEMO_MEMO}, headers=ha).json()["job_id"]
    second = client.post("/verifications", json={"text": DEMO_MEMO}, headers=ha).json()["job_id"]

    jobs = client.get("/me/jobs", headers=ha)
    assert jobs.status_code == 200
    body = jobs.json()
    assert [j["job_id"] for j in body] == [second, first]  # newest first
    top = body[0]
    assert set(top) == {
        "job_id",
        "status",
        "stage",
        "report_id",
        "created_at",
        "title",
        "memo_snippet",
    }
    assert top["status"] == "queued"
    assert top["report_id"] is None
    assert top["memo_snippet"] == " ".join(DEMO_MEMO.split())[:80]
    assert top["title"] == ""  # not yet titled (titling runs in the worker)

    # A different user does not see userA's jobs.
    other = client.get("/me/jobs", headers={"Authorization": "Bearer tokB"})
    assert other.status_code == 200
    assert other.json() == []


# --- auth: dark-ship vs enabled ---


def test_dark_ship_needs_no_token(make_client):
    client, _ = make_client(verifier=None)
    assert client.get("/queue").status_code == 200  # open, default principal


def test_enabled_auth_rejects_missing_and_bad_tokens(make_client):
    client, _ = make_client(verifier=FakeVerifier({"tokA": "userA"}))
    assert client.get("/queue").status_code == 401  # no token
    assert client.get("/queue", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_enabled_auth_forbids_cross_user_report_access(make_client):
    client, _ = make_client(verifier=FakeVerifier({"tokA": "userA", "tokB": "userB"}))
    job_id = client.post(
        "/verifications", json={"text": DEMO_MEMO}, headers={"Authorization": "Bearer tokA"}
    ).json()["job_id"]
    report_id = _complete(job_id)

    forbidden = client.get(f"/reports/{report_id}", headers={"Authorization": "Bearer tokB"})
    assert forbidden.status_code == 403
    allowed = client.get(f"/reports/{report_id}", headers={"Authorization": "Bearer tokA"})
    assert allowed.status_code == 200


# --- health ---


def test_health_is_public_and_touches_nothing(make_client):
    # Present even with auth enabled, and requires no token: the gateway exposes it
    # without the authorizer as the uptime probe.
    client, _ = make_client(verifier=FakeVerifier({}))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --- freemium quota ---


class TieredVerifier(FakeVerifier):
    def __init__(self, mapping: dict[str, str], tier: str = "free") -> None:
        super().__init__(mapping)
        self._tier = tier

    def tier(self, token: str) -> str:
        return self._tier


def test_free_tier_402s_after_two_this_week(make_client):
    client, queue = make_client(verifier=TieredVerifier({"tok": "u1"}, tier="free"))
    h = {"Authorization": "Bearer tok"}
    assert client.post("/verifications", json={"text": DEMO_MEMO}, headers=h).status_code == 202
    assert client.post("/verifications", json={"text": DEMO_MEMO}, headers=h).status_code == 202
    third = client.post("/verifications", json={"text": DEMO_MEMO}, headers=h)
    assert third.status_code == 402
    detail = third.json()["detail"]
    assert detail["tier"] == "free"
    assert detail["limit"] == 2
    assert detail["remaining"] == 0
    # Rejected before cost: only the two allowed jobs were enqueued.
    assert len(queue.messages) == 2


def test_me_usage_reports_tier_and_remaining(make_client):
    client, _ = make_client(verifier=TieredVerifier({"tok": "u2"}, tier="free"))
    h = {"Authorization": "Bearer tok"}
    client.post("/verifications", json={"text": DEMO_MEMO}, headers=h)
    usage = client.get("/me/usage", headers=h).json()
    assert usage["tier"] == "free"
    assert usage["used"] == 1
    assert usage["remaining"] == 1


def test_pro_tier_is_not_blocked_at_two(make_client):
    client, _ = make_client(verifier=TieredVerifier({"tok": "p"}, tier="pro"))
    h = {"Authorization": "Bearer tok"}
    for _ in range(3):
        assert client.post("/verifications", json={"text": DEMO_MEMO}, headers=h).status_code == 202
