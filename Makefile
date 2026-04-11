UV := uv
PYTHON := $(UV) run python
UVICORN := $(UV) run uvicorn
HOST ?= 127.0.0.1
PORT ?= 8000
MCP_API_TOKEN ?=

RESET := \033[0m
BOLD := \033[1m
BLUE := \033[34m
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m

.DEFAULT_GOAL := help

.PHONY: help setup run run-private test lint

help:
	@printf "\n"
	@printf "$(BOLD)$(BLUE)FastMCP local commands$(RESET)\n"
	@printf "$(BLUE)======================$(RESET)\n\n"
	@printf "$(BOLD)$(CYAN)Environment setup$(RESET)\n"
	@printf "  make setup\n"
	@printf "    Create the local uv environment and sync dependencies.\n\n"
	@printf "$(BOLD)$(CYAN)Run locally$(RESET)\n"
	@printf "  make run\n"
	@printf "    Start the MCP server locally without auth.\n"
	@printf "    Variables:\n"
	@printf "      HOST=$(HOST)\n"
	@printf "      PORT=$(PORT)\n\n"
	@printf "  make run-private MCP_API_TOKEN=dev-secret-token\n"
	@printf "    Start the MCP server locally with bearer-token auth.\n"
	@printf "    Variables:\n"
	@printf "      HOST=$(HOST)\n"
	@printf "      PORT=$(PORT)\n"
	@printf "      MCP_API_TOKEN=%s\n\n" "$(if $(MCP_API_TOKEN),<provided>,<required>)"
	@printf "$(BOLD)$(CYAN)Developer checks$(RESET)\n"
	@printf "  make test\n"
	@printf "    Run the backend test suite.\n\n"
	@printf "  make lint\n"
	@printf "    Run Ruff checks.\n\n"

setup:
	$(UV) venv
	$(UV) sync

run:
	$(UVICORN) index:app --reload --host $(HOST) --port $(PORT)

run-private:
	@if [ -z "$(MCP_API_TOKEN)" ]; then \
		printf "\n$(BOLD)$(YELLOW)MCP_API_TOKEN is required for make run-private.$(RESET)\n"; \
		printf "Example: make run-private MCP_API_TOKEN=dev-secret-token\n\n"; \
		exit 1; \
	fi
	MCP_API_TOKEN="$(MCP_API_TOKEN)" $(UVICORN) index:app --reload --host $(HOST) --port $(PORT)

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
