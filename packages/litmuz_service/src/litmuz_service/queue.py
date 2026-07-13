"""Job queue abstraction shared by the API, worker and MCP adapters.

Adapters depend on the Queue protocol; unit tests use InMemoryQueue and never touch AWS.
SqsQueue lazily imports boto3 so importing this module needs no AWS dependency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol


class Queue(Protocol):
    def enqueue(self, job_id: str) -> None: ...


@dataclass
class InMemoryQueue:
    """A queue for tests and local dev. `receive` drains and returns the pending job ids."""

    messages: list[str] = field(default_factory=list)

    def enqueue(self, job_id: str) -> None:
        self.messages.append(job_id)

    def receive(self) -> list[str]:
        drained = list(self.messages)
        self.messages.clear()
        return drained


@dataclass
class SqsQueue:
    queue_url: str
    client: object = None

    def __post_init__(self) -> None:
        if self.client is None:
            import boto3

            self.client = boto3.client("sqs")

    def enqueue(self, job_id: str) -> None:
        self.client.send_message(  # type: ignore[attr-defined]
            QueueUrl=self.queue_url, MessageBody=json.dumps({"job_id": job_id})
        )
