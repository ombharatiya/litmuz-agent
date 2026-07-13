# Worker container image. Build from the repo root so the whole uv workspace is in context:
#   docker build -f apps/worker/Dockerfile -t litmuz-worker .
FROM python:3.11-slim AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY apps ./apps

# Resolve the locked environment for just the worker (its path deps live in packages/).
RUN uv sync --frozen --no-dev --package litmuz-worker

FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# A non-root runtime user.
RUN useradd --create-home --uid 10001 litmuz
WORKDIR /app
COPY --from=build /app /app
USER litmuz

CMD ["python", "-m", "litmuz_worker"]
