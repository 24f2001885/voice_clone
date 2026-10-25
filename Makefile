.DEFAULT_GOAL := help

.PHONY: help lint format typecheck test test-gpu coverage lock build run docker-test doctor

help: ## Show this help message
	@echo "VoxClone CLI Development & Automation Pipeline"
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

lint: ## Run ruff and black code quality checks
	ruff check src tests
	black --check src tests

format: ## Automatically format and fix source files with ruff and black
	ruff check --fix src tests
	black src tests

typecheck: ## Run mypy static type checking in strict mode
	mypy

test: ## Run unit and integration tests offline (excluding GPU tests)
	pytest

test-gpu: ## Run GPU-dependent tests on CUDA host
	pytest -m gpu

coverage: ## Run pytest with coverage report and fail under 85%
	pytest --cov=src/voxclone --cov-report=term-missing --cov-fail-under=85

lock: ## Compile requirements.in into requirements.lock using pip-compile
	pip-compile requirements.in -o requirements.lock

build: ## Build runtime Docker image voxclone:latest
	docker compose build

run: ## Run interactive VoxClone CLI container
	docker compose run --rm voxclone

docker-test: ## Run offline test suite inside isolated Docker test container
	docker compose -f docker-compose.test.yml run --rm tests make test

doctor: ## Run host environment pre-flight diagnostics
	bash scripts/doctor.sh
