# apps/mcp: MCP server

An [MCP](https://modelcontextprotocol.io) server (built on the Python `mcp` SDK) that exposes
Litmuz verification as tools any Claude-powered agent can call:

- `verify_output` — submit an agent memo for verification; returns a `job_id` to poll.
- `verify_claim` — verify a single claim synchronously; returns the verdict and
  `requires_human_review`.
- `get_job_status` — status and per-stage progress of a verification job.
- `get_provenance` — fetch a stored provenance report by id (owner-only).

It runs over **stdio** (local dev) and **Streamable HTTP** (hosted). Over HTTP the principal
is bound per request from the bearer token; a `TokenVerifier` can be injected to enforce
per-user authorization, or it runs open when none is configured. The tools carry no logic —
they call the same `litmuz_core` pipeline as the REST adapter. See `src/litmuz_mcp/`.
