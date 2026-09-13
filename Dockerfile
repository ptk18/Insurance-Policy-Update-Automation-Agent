FROM ghcr.io/astral-sh/uv:0.11.14 AS uv
FROM python:3.13-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    POLICY_UPDATE_ENV_FILE=/nonexistent SCHEMA_MODE=verify WORKER_MODE=external
USER app
EXPOSE 8000
CMD ["uvicorn", "policy_update.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
