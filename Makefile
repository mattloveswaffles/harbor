# Harbor: one entry point for local work and CI. Needs uv (server) and bun (app).
.DEFAULT_GOAL := help
.PHONY: help install dev dev-server dev-app build check check-server check-app format docker seed clean

help: ## Show the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

install: ## Install server and app dependencies
	cd server && uv sync
	cd app && bun install

dev: build ## Run the server on :8000 and rebuild the app on every save
	$(MAKE) -j2 dev-server dev-app

dev-server:
	cd server && uv run uvicorn harbor.main:app --reload --port 8000

dev-app:
	cd app && bun run dev

build: ## Build the website into app/dist
	cd app && bun run build

check: check-server check-app ## Lint, type-check, test and build everything (what CI runs)

check-server: ## Server: ruff lint + format check, pytest
	cd server && uv run ruff check && uv run ruff format --check && uv run pytest

check-app: ## App: biome, tsc, bun test, build
	cd app && bun run lint && bun run typecheck && bun run test && bun run build

format: ## Auto-fix formatting and safe lint issues
	cd server && uv run ruff check --fix && uv run ruff format
	cd app && bun run format

docker: ## Build and run everything in Docker on :3000
	docker build -t harbor .
	docker run --rm -p 3000:3000 --env-file $(if $(wildcard .env),.env,.env.example) harbor

seed: ## Seed a household into the Milton storm and open the app signed in (server on :3000)
	./seed.sh

clean: ## Remove build output and caches
	rm -rf app/dist server/.pytest_cache server/.ruff_cache
