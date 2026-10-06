# syntax=docker/dockerfile:1
# Targets: api, worker (CPU, FakeEngine), worker-gpu (CUDA torch + diffusers for the RTX 3090).

FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN useradd --uid 1000 --create-home app \
    && mkdir -p /data && chown app:app /data

FROM base AS cpu-deps
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

FROM cpu-deps AS api
USER app
EXPOSE 8000
CMD ["uvicorn", "vidgen.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM cpu-deps AS worker
USER app
CMD ["arq", "vidgen.worker.main.WorkerSettings"]

# PyTorch cu128 wheels bundle the CUDA runtime; the host only needs the NVIDIA driver
# and the NVIDIA Container Toolkit.
FROM base AS worker-gpu
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra gpu --no-install-project
COPY README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra gpu
ENV HF_HOME=/models
USER app
CMD ["arq", "vidgen.worker.main.WorkerSettings"]
