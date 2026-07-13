# apps/worker: async pipeline worker

A queue-consuming worker that runs the `litmuz_core` pipeline off the request path. It
long-polls a job queue, runs each job to completion, persists provenance to Postgres, and
writes per-stage progress.

`run_job` is idempotent, so at-least-once redelivery is safe: a message whose job raises is
left on the queue for redelivery and, after the configured attempts, dead-lettering.

The core `handle_message` / `WorkerContext` logic is queue-agnostic (see
`src/litmuz_worker/worker.py`); the shipped `main()` loop consumes an SQS queue via `boto3`.
