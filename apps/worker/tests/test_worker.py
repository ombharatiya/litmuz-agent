"""The worker runs a job from an SQS message body and is idempotent (Phase 4)."""

import json

from litmuz_core.config import Config
from litmuz_core.testing import (
    DEMO_MEMO,
    FakeMetadataClient,
    FakePipelineLlm,
    FakeRetrievalClient,
)
from litmuz_service.jobs import submit
from litmuz_service.queue import InMemoryQueue
from litmuz_store import get_job
from litmuz_store.provision import API_ROLE, APP_ROLE
from litmuz_store.testing import connect
from litmuz_worker.worker import WorkerContext, handle_message


def _ctx() -> WorkerContext:
    return WorkerContext(
        app_conn_factory=lambda: connect(APP_ROLE),
        llm=FakePipelineLlm(),
        metadata_client=FakeMetadataClient(),
        retrieval_client=FakeRetrievalClient(),
        config=Config(),
    )


def _reports_count() -> int:
    with connect(API_ROLE) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM reports")
        return cur.fetchone()[0]


def test_handle_message_runs_the_job(app_conn):
    job_id = submit(memo=DEMO_MEMO, user_sub="u1", app_conn=app_conn, queue=InMemoryQueue())
    report_id = handle_message(json.dumps({"job_id": job_id}), _ctx())
    assert report_id is not None
    with connect(API_ROLE) as conn:
        job = get_job(conn, job_id)
    assert job["status"] == "completed"
    assert str(job["report_id"]) == report_id


def test_handle_message_is_idempotent_on_redelivery(app_conn):
    job_id = submit(memo=DEMO_MEMO, user_sub="u1", app_conn=app_conn, queue=InMemoryQueue())
    body = json.dumps({"job_id": job_id})
    first = handle_message(body, _ctx())
    second = handle_message(body, _ctx())  # redelivery
    assert first == second
    assert _reports_count() == 1
