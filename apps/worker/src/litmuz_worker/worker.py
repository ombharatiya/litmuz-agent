"""Fargate worker: long-poll SQS and run each job to completion.

run_job is idempotent, so an at-least-once redelivery is safe. A message whose job raises is
not deleted; SQS makes it visible again and, after the configured attempts, dead-letters it
(AC-JOB-3). The heavy work happens here, off the API request path.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

from litmuz_core.config import Config
from litmuz_service.jobs import run_job

log = logging.getLogger("litmuz.worker")


@dataclass
class WorkerContext:
    app_conn_factory: Callable[[], object]
    llm: object
    metadata_client: object
    retrieval_client: object
    config: Config


def handle_message(body: str, ctx: WorkerContext) -> str | None:
    """Run the job named in one SQS message body. Returns the report id (or None if skipped)."""
    job_id = json.loads(body)["job_id"]
    with ctx.app_conn_factory() as conn:
        return run_job(
            job_id,
            app_conn=conn,
            llm=ctx.llm,
            metadata_client=ctx.metadata_client,
            retrieval_client=ctx.retrieval_client,
            config=ctx.config,
        )


def _context_from_env() -> tuple[WorkerContext, object, str]:  # pragma: no cover
    import os

    import boto3
    import psycopg

    from litmuz_core.cite.clients import NcbiCrossrefClient
    from litmuz_core.llm import AnthropicClient
    from litmuz_core.retrieve.clients import NcbiPmcClient

    config = Config.from_env()
    host = os.environ["DB_HOST"]
    port = int(os.environ.get("DB_PORT", "5432"))
    dbname = os.environ.get("DB_NAME", "litmuz")
    user = os.environ.get("LITMUZ_APP_USER", "litmuz_app")
    password = os.environ["LITMUZ_APP_PASSWORD"]

    def app_conn_factory():
        return psycopg.connect(host=host, port=port, dbname=dbname, user=user, password=password)

    ctx = WorkerContext(
        app_conn_factory=app_conn_factory,
        llm=AnthropicClient(config),
        metadata_client=NcbiCrossrefClient(config),
        retrieval_client=NcbiPmcClient(config),
        config=config,
    )
    return ctx, boto3.client("sqs"), os.environ["SQS_QUEUE_URL"]


def main() -> None:  # pragma: no cover  (the SQS receive loop is integration, not unit-tested)
    logging.basicConfig(level=logging.INFO)
    ctx, sqs, queue_url = _context_from_env()
    log.info("worker started; polling %s", queue_url)
    while True:
        resp = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=20)
        for message in resp.get("Messages", []):
            try:
                handle_message(message["Body"], ctx)
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
            except Exception:
                # Do not delete: SQS redelivers and eventually dead-letters the message.
                log.exception("job failed; leaving the message for redrive")
