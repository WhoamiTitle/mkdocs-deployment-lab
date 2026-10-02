PYTHON ?= .venv/bin/python
UV ?= uv
BIN_DIR ?= .venv/bin
SITE_DIR ?= site
LOCAL_DEPLOYMENT_ROOT ?= .local-deploy/state
LOCAL_PUBLIC_PATH ?= .local-deploy/public-site
HELIOS_SANDBOX_BASE_URL ?= https://se.ifmo.ru/~s507353/mkdocs-deployment-lab-sandbox/
HELIOS_PRODUCTION_URL ?= https://se.ifmo.ru/~s507353/mkdocs-deployment-lab/

.PHONY: setup lint architecture dependencies slots typecheck test audit build offline-check check serve deploy-local preview-local rollback-local benchmark-local test-helios-sandbox

setup:
	$(UV) sync --locked

lint:
	$(PYTHON) -m ruff check scripts src tests
	$(PYTHON) -m ruff format --check scripts src tests
	$(BIN_DIR)/tombi format --check pyproject.toml
	$(BIN_DIR)/tombi lint pyproject.toml
	$(PYTHON) -m codespell_lib README.md config docs scripts src tests

architecture:
	$(BIN_DIR)/lint-imports

dependencies:
	$(BIN_DIR)/uv lock --check
	$(BIN_DIR)/deptry .

slots:
	$(PYTHON) -m slotscheck src/publication_pipeline

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest \
		--cov=publication_pipeline \
		--cov-report=term-missing \
		--cov-fail-under=80

audit:
	bash scripts/pip_audit.sh

build:
	$(PYTHON) -m publication_pipeline build --site-dir $(SITE_DIR)

offline-check:
	$(PYTHON) -m publication_pipeline offline-check --site-dir $(SITE_DIR)

check: lint architecture dependencies slots typecheck test build offline-check

serve:
	$(PYTHON) -m mkdocs serve

deploy-local: build
	$(PYTHON) -m publication_pipeline deploy-local \
		--site-dir $(SITE_DIR) \
		--deployment-root $(LOCAL_DEPLOYMENT_ROOT) \
		--public-path $(LOCAL_PUBLIC_PATH)

preview-local: build
	$(PYTHON) -m publication_pipeline preview-local \
		--site-dir $(SITE_DIR) \
		--deployment-root $(LOCAL_DEPLOYMENT_ROOT) \
		--public-path $(LOCAL_PUBLIC_PATH) \
		--branch "$${BRANCH:-preview/local}"

rollback-local:
	$(PYTHON) -m publication_pipeline rollback-local \
		--deployment-root $(LOCAL_DEPLOYMENT_ROOT) \
		--public-path $(LOCAL_PUBLIC_PATH)

benchmark-local:
	$(PYTHON) -m scripts.measure_publication local \
		--runs "$${RUNS:-5}" \
		--run-start "$${RUN_START:-1}"

test-helios-sandbox:
	$(PYTHON) -m scripts.verify_helios_resilience \
		--base-url "$(HELIOS_SANDBOX_BASE_URL)" \
		--production-url "$(HELIOS_PRODUCTION_URL)" \
		--cleanup
