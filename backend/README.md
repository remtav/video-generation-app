# vidgen backend

One Python project with three parts:

- `vidgen.api`: the FastAPI HTTP API.
- `vidgen.worker`: the arq worker that runs the video engine on the GPU.
- `vidgen.db`: SQLAlchemy models, shared by both. Alembic migrations live in `migrations/`.

```bash
uv sync                          # API + worker (CPU, FakeEngine) + dev tools
uv run ruff check . && uv run ruff format --check . && uv run mypy src tests
uv run pytest                    # DB tests run when VIDGEN_DATABASE_URL is set
uv run uvicorn vidgen.api.main:app --reload
uv run arq vidgen.worker.main.WorkerSettings
```
