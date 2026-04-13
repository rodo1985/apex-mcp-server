UV := uv
PYTHON := $(UV) run python
UVICORN := $(UV) run uvicorn
HOST ?= 127.0.0.1
PORT ?= 8000
POSTGRES_DB ?= apex_mcp_server
POSTGRES_USER ?= apex
POSTGRES_PASSWORD ?= apex
POSTGRES_PORT ?= 54329
MCP_API_TOKEN ?=
DATABASE_URL ?= postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@127.0.0.1:$(POSTGRES_PORT)/$(POSTGRES_DB)

RESET := \033[0m
BOLD := \033[1m
BLUE := \033[34m
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m

.DEFAULT_GOAL := help

.PHONY: help setup db-up run run-private docker-up docker-down test lint

help:
	@printf "\n"
	@printf "$(BOLD)$(BLUE)FastMCP local commands$(RESET)\n"
	@printf "$(BLUE)======================$(RESET)\n\n"
	@printf "$(BOLD)$(CYAN)Environment setup$(RESET)\n"
	@printf "  make setup\n"
	@printf "    Create the local uv environment and sync dependencies.\n\n"
	@printf "$(BOLD)$(CYAN)Database$(RESET)\n"
	@printf "  make db-up\n"
	@printf "    Start the local Postgres container and wait until it is ready.\n"
	@printf "    Variables:\n"
	@printf "      POSTGRES_DB=$(POSTGRES_DB)\n"
	@printf "      POSTGRES_USER=$(POSTGRES_USER)\n"
	@printf "      POSTGRES_PASSWORD=$(POSTGRES_PASSWORD)\n"
	@printf "      POSTGRES_PORT=$(POSTGRES_PORT)\n\n"
	@printf "$(BOLD)$(CYAN)Run on host$(RESET)\n"
	@printf "  make run\n"
	@printf "    Start the MCP server locally without auth against Postgres.\n"
	@printf "    Variables:\n"
	@printf "      HOST=$(HOST)\n"
	@printf "      PORT=$(PORT)\n"
	@printf "      DATABASE_URL=$(DATABASE_URL)\n\n"
	@printf "  make run-private MCP_API_TOKEN=dev-secret-token\n"
	@printf "    Start the MCP server locally with bearer-token auth.\n"
	@printf "    Variables:\n"
	@printf "      HOST=$(HOST)\n"
	@printf "      PORT=$(PORT)\n"
	@printf "      DATABASE_URL=$(DATABASE_URL)\n"
	@printf "      MCP_API_TOKEN=%s\n\n" "$(if $(MCP_API_TOKEN),<provided>,<required>)"
	@printf "$(BOLD)$(CYAN)Run in Docker$(RESET)\n"
	@printf "  make docker-up\n"
	@printf "    Build and start the app and Postgres containers.\n\n"
	@printf "  make docker-down\n"
	@printf "    Stop the Compose stack.\n\n"
	@printf "$(BOLD)$(CYAN)Developer checks$(RESET)\n"
	@printf "  make test\n"
	@printf "    Run the backend test suite. Starts Postgres automatically when Docker is available.\n\n"
	@printf "  make lint\n"
	@printf "    Run Ruff checks.\n\n"

setup:
	$(UV) venv
	$(UV) sync

db-up:
	@printf "\n$(BOLD)$(GREEN)Starting local Postgres...$(RESET)\n"
	@docker compose up -d db
	@until docker compose exec -T db pg_isready -U "$(POSTGRES_USER)" -d "$(POSTGRES_DB)" >/dev/null 2>&1; do \
		printf "$(YELLOW)Waiting for Postgres to become ready...$(RESET)\n"; \
		sleep 1; \
	done
	@printf "$(GREEN)Postgres is ready on localhost:$(POSTGRES_PORT).$(RESET)\n\n"

run:
	@set -a; \
	if [ -f .env.local ]; then . ./.env.local; fi; \
	set +a; \
	DATABASE_URL="$${DATABASE_URL:-$(DATABASE_URL)}" \
	$(UVICORN) index:app --reload --host $(HOST) --port $(PORT)

run-private:
	@if [ -z "$(MCP_API_TOKEN)" ]; then \
		printf "\n$(BOLD)$(YELLOW)MCP_API_TOKEN is required for make run-private.$(RESET)\n"; \
		printf "Example: make run-private MCP_API_TOKEN=dev-secret-token\n\n"; \
		exit 1; \
	fi
	@set -a; \
	if [ -f .env.local ]; then . ./.env.local; fi; \
	set +a; \
	MCP_API_TOKEN="$(MCP_API_TOKEN)" \
	DATABASE_URL="$${DATABASE_URL:-$(DATABASE_URL)}" \
	$(UVICORN) index:app --reload --host $(HOST) --port $(PORT)

docker-up:
	@printf "\n$(BOLD)$(GREEN)Starting Docker Compose stack...$(RESET)\n"
	docker compose up --build -d app db

docker-down:
	@printf "\n$(BOLD)$(GREEN)Stopping Docker Compose stack...$(RESET)\n"
	docker compose down

test:
	@if docker info >/dev/null 2>&1; then \
		$(MAKE) db-up; \
	else \
		printf "\n$(BOLD)$(YELLOW)Docker daemon not available. Running pytest without auto-starting Postgres.$(RESET)\n\n"; \
	fi
	@set -a; \
	if [ -f .env.local ]; then . ./.env.local; fi; \
	set +a; \
	DATABASE_URL="$${DATABASE_URL:-$(DATABASE_URL)}" \
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
