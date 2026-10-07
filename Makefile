COMPOSE_GPU := docker compose -f compose.yml -f compose.gpu.yml

.PHONY: up up-gpu down logs ps health smoke test lint fmt

up:        ## Full stack with the CPU FakeEngine (any machine)
	docker compose up -d --build --wait

up-gpu:    ## Full stack with the CUDA worker (RTX 3090 host)
	$(COMPOSE_GPU) up -d --build --wait

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

health:
	curl -fsS http://127.0.0.1:8000/api/health; echo

smoke:     ## End-to-end check of the running stack through the frontend
	scripts/smoke_test.sh http://127.0.0.1:3000

test:      ## Unit tests (backend DB tests need VIDGEN_DATABASE_URL / VIDGEN_REDIS_URL)
	cd backend && uv run pytest
	cd frontend && npm test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy src tests
	cd frontend && npm run lint && npm run format:check && npm run typecheck

fmt:
	cd backend && uv run ruff check --fix . && uv run ruff format .
	cd frontend && npm run format
