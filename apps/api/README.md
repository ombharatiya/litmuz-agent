# apps/api: REST adapter

A FastAPI adapter over the verification service. It validates and enqueues jobs, reads job
status and reports, and serves the human review queue. It calls `litmuz_service` and
`litmuz_store` and contains **no verification logic** of its own.

The app is constructed from an injected `ApiContext` (DB connection factories, a `Queue`, an
optional token verifier), so it is transport- and infrastructure-agnostic:

- With **no verifier** configured the API runs open ("dark-ship") and keys everything to a
  default principal.
- With a verifier, a missing or invalid bearer token is `401` and cross-user access is `403`.

See `src/litmuz_api/app.py` for the routes and `tests/test_app.py` for an end-to-end
`TestClient` example that wires the app to an `InMemoryQueue`.
