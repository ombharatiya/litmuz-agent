"""AC-NFR-1: record p50/p95 latency over a warm-cache fixture and assert the budget.

The model and NCBI are mocked (a warm cache), so this measures the pipeline plumbing, not
real API latency, which is an integration concern. The budget is the pass line.
"""

import statistics
import time

from litmuz_core.config import Config
from litmuz_core.testing import (
    DEMO_MEMO,
    FakeMetadataClient,
    FakePipelineLlm,
    FakeRetrievalClient,
)
from litmuz_service.jobs import run_job, submit
from litmuz_service.queue import InMemoryQueue
from litmuz_store.provision import APP_ROLE
from litmuz_store.testing import connect

FULL_MEMO_P95_BUDGET_S = 300.0
FULL_MEMO_P50_BUDGET_S = 180.0


def test_full_memo_latency_within_budget(app_conn):
    durations: list[float] = []
    for _ in range(5):
        with connect(APP_ROLE) as conn:
            job_id = submit(memo=DEMO_MEMO, user_sub="u1", app_conn=conn, queue=InMemoryQueue())
            start = time.perf_counter()
            run_job(
                job_id,
                app_conn=conn,
                llm=FakePipelineLlm(),
                metadata_client=FakeMetadataClient(),
                retrieval_client=FakeRetrievalClient(),
                config=Config(),
            )
            durations.append(time.perf_counter() - start)

    durations.sort()
    p50 = statistics.median(durations)
    p95 = durations[-1]  # highest of five approximates p95
    assert p95 <= FULL_MEMO_P95_BUDGET_S, f"p95 {p95:.3f}s over budget"
    assert p50 <= FULL_MEMO_P50_BUDGET_S, f"p50 {p50:.3f}s over budget"
