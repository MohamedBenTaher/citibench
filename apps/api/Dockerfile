FROM python:3.12-slim

# uv is the package manager: fast resolver, retries, deterministic installs.
COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /uvx /usr/local/bin/

WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=180 \
    UV_COMPILE_BYTECODE=1

# Lock, not requirements: one pinned resolution shared with CI/local.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY apps/api ./apps/api

WORKDIR /app/apps/api
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
