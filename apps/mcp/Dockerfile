# MCP server container image (Streamable HTTP transport). Build from the repo root:
#   docker build -f apps/mcp/Dockerfile -t litmuz-mcp .
FROM python:3.11-slim AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY apps ./apps

RUN uv sync --frozen --no-dev --package litmuz-mcp

FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    MCP_TRANSPORT=http

RUN useradd --create-home --uid 10001 litmuz
WORKDIR /app
COPY --from=build /app /app
USER litmuz

EXPOSE 8080
CMD ["python", "-m", "litmuz_mcp"]
