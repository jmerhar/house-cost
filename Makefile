.PHONY: help install dev up down logs shell build test test-backend test-frontend test-bruno test-samples \
        coverage lint openapi contract check migrate revision db-shell lockfile release clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*##|^##@' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5); next} {printf "  \033[36mmake %-16s\033[0m %s\n", $$1, $$2}'

##@ Setup

# node_modules is installed through whatever registry this machine's npm reaches, without touching
# the lockfile, which records only the public registry.
install: ## Create the backend virtualenv and install the frontend packages
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install --quiet --upgrade pip
	backend/.venv/bin/pip install --quiet -e "backend[test]"
	cd frontend && npm ci --no-audit --no-fund --registry="$$(cd / && npm config get registry)"

##@ Development

dev: ## Start the stack with hot reload (API on :8000, interface on :5173)
	bin/dev.sh

up: ## Build and start the production stack
	docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d
	@echo "Interface: http://127.0.0.1:8000"

down: ## Stop the stack, keeping the data
	docker compose down

logs: ## Follow the container's log
	docker compose logs -f

shell: ## Open a shell in the running container
	docker compose exec house-cost sh

build: ## Build the image without starting anything
	docker compose -f docker-compose.yml -f docker-compose.build.yml build

##@ Testing

test: test-backend test-frontend ## Run both test suites

test-backend: ## Run the backend suite (ARGS pass through to pytest)
	bin/test-backend.sh $(ARGS)

test-frontend: ## Type-check the interface and run its suite
	bin/test-frontend.sh $(ARGS)

test-bruno: ## Run the Bruno collection against the real API
	bin/test-bruno.sh

test-samples: ## Read the real bills in samples/ (kept out of git) and check what they give
	SAMPLES_DIR="$(CURDIR)/samples" bin/test-backend.sh tests/test_extraction.py -k real_samples -v

coverage: ## Run both suites with coverage and print the combined summary
	bin/coverage.sh --format md

lint: ## ShellCheck, ruff, lockfile, versions, compose files
	bin/lint.sh

openapi: ## Re-export the API schema and regenerate the interface's types
	bin/openapi.sh

contract: openapi ## Check the committed schema and generated types are up to date
	@git diff --exit-code frontend/openapi.json frontend/src/lib/api-types.ts \
		|| { echo; echo "The schema changed. Commit the regenerated files above."; exit 1; }
	@echo "schema and types are current"

check: lint contract coverage test-bruno ## Everything (gate a commit on this)

##@ Database

migrate: ## Apply migrations to the development database
	bin/migrate.sh

revision: ## Generate a migration from the models (usage: make revision m="what changed")
	bin/migrate.sh revision --autogenerate -m "$(m)"

db-shell: ## Open a SQLite shell on the development database
	sqlite3 data/house-cost.db

##@ Release

lockfile: ## Regenerate package-lock.json (Linux binaries, public registry URLs)
	bin/lockfile.sh

release: ## Cut a release from CHANGELOG.md (usage: make release VERSION=X.Y.Z; then push both)
	bin/release.sh $(VERSION)

clean: ## Remove build and coverage output (all regenerable)
	rm -rf backend/htmlcov backend/coverage.xml backend/coverage.json backend/.coverage \
	       backend/junit frontend/coverage frontend/dist frontend/src/paraglide \
	       coverage-upload .coverage-report.py
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
