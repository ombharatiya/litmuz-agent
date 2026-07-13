"""FastMCP wiring for the four Litmuz tools over stdio (dev) and Streamable HTTP (hosted).

The tools carry no logic; they call the plain functions in tools.py with the session's
principal. The per-user authorization is enforced there (a cross-user id is a typed
not-found). For Streamable HTTP the principal is bound per request from the bearer token by
create_http_app; for stdio it is a configured principal.
"""

from __future__ import annotations

import contextvars
import os
from collections.abc import Callable

from litmuz_core.config import Config

from .tools import (
    McpContext,
    NotFound,
    get_job_status,
    get_provenance,
    verify_claim,
    verify_output,
)

_principal_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "litmuz_principal", default="local"
)


def _not_found_to_error(func, **kwargs) -> dict:
    try:
        return func(**kwargs)
    except NotFound as exc:
        return {"error": "not_found", "detail": str(exc)}


def build_server(ctx: McpContext, principal_provider: Callable[[], str] | None = None):
    from mcp.server.fastmcp import FastMCP

    provider = principal_provider or _principal_var.get
    mcp = FastMCP("litmuz")

    @mcp.tool(name="verify_output")
    def verify_output_tool(text: str, sources: list[str] | None = None) -> dict:
        """Submit an agent memo for verification. Returns a job_id to poll with get_job_status."""
        return verify_output(ctx, principal=provider(), text=text, sources=sources)

    @mcp.tool(name="get_job_status")
    def get_job_status_tool(job_id: str) -> dict:
        """Get the status and per-stage progress of a verification job."""
        return _not_found_to_error(get_job_status, ctx=ctx, principal=provider(), job_id=job_id)

    @mcp.tool(name="get_provenance")
    def get_provenance_tool(report_id: str) -> dict:
        """Retrieve a stored provenance report by id (only the owner may read it)."""
        return _not_found_to_error(
            get_provenance, ctx=ctx, principal=provider(), report_id=report_id
        )

    @mcp.tool(name="verify_claim")
    def verify_claim_tool(
        claim: str, citation: str | None = None, sources: list[str] | None = None
    ) -> dict:
        """Verify one claim synchronously. Returns the verdict and requires_human_review."""
        return verify_claim(
            ctx, principal=provider(), claim=claim, citation=citation, sources=sources
        )

    return mcp


def _context_from_env() -> McpContext:  # pragma: no cover
    import psycopg

    from litmuz_core.cite.clients import NcbiCrossrefClient
    from litmuz_core.llm import AnthropicClient
    from litmuz_core.retrieve.clients import NcbiPmcClient
    from litmuz_service import SqsQueue

    config = Config.from_env()
    host = os.environ["DB_HOST"]
    port = int(os.environ.get("DB_PORT", "5432"))
    dbname = os.environ.get("DB_NAME", "litmuz")

    def factory(user: str, password: str):
        def make():
            return psycopg.connect(
                host=host, port=port, dbname=dbname, user=user, password=password
            )

        return make

    return McpContext(
        app_conn_factory=factory(
            os.environ.get("LITMUZ_APP_USER", "litmuz_app"), os.environ["LITMUZ_APP_PASSWORD"]
        ),
        api_conn_factory=factory(
            os.environ.get("LITMUZ_API_USER", "litmuz_api"), os.environ["LITMUZ_API_PASSWORD"]
        ),
        queue=SqsQueue(os.environ["SQS_QUEUE_URL"]),
        config=config,
        llm=AnthropicClient(config),
        metadata_client=NcbiCrossrefClient(config),
        retrieval_client=NcbiPmcClient(config),
    )


def create_http_app(ctx: McpContext, verifier):  # pragma: no cover
    """Streamable HTTP app that binds the per-request principal from the bearer token."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import PlainTextResponse

    server = build_server(ctx)
    app = server.streamable_http_app()

    class _Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            header = request.headers.get("authorization", "")
            token = header[7:].strip() if header.lower().startswith("bearer ") else None
            if verifier is not None:
                if not token:
                    return PlainTextResponse("unauthorized", status_code=401)
                try:
                    _principal_var.set(verifier.verify(token))
                except Exception:
                    return PlainTextResponse("unauthorized", status_code=401)
            return await call_next(request)

    app.add_middleware(_Auth)
    return app


def main() -> None:  # pragma: no cover  (transport run loop is integration, not unit-tested)
    ctx = _context_from_env()
    principal = os.environ.get("LITMUZ_PRINCIPAL", "local")
    if os.environ.get("MCP_TRANSPORT", "stdio") == "http":
        import uvicorn

        # Dark-ship: the HTTP transport runs open (no verifier), keying everything to the
        # default principal. Inject a TokenVerifier (anything with a `.verify(token) -> sub`
        # method) into create_http_app to enforce per-user auth in a hosted deployment.
        uvicorn.run(create_http_app(ctx, verifier=None), host="0.0.0.0", port=8080)
    else:
        build_server(ctx, principal_provider=lambda: principal).run(transport="stdio")
