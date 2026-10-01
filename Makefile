PYTHON ?= .venv/bin/python
SITE_DIR ?= site
LOCAL_STATE_ROOT ?= .local-deploy/state
LOCAL_PUBLIC_PATH ?= .local-deploy/public-site

.PHONY: setup lint typecheck test build offline-check check serve deploy-local preview-local rollback-local benchmark-local

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install pip==26.2.1
	.venv/bin/python -m pip install --requirement requirements.txt
	.venv/bin/python -m pip install --no-deps --editable .

lint:
	$(PYTHON) -m ruff check scripts src tests
	$(PYTHON) -m ruff format --check scripts src tests
	$(PYTHON) -m codespell_lib README.md config docs scripts src tests

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest

build:
	$(PYTHON) -m publication_pipeline build --site-dir $(SITE_DIR)

offline-check:
	$(PYTHON) -m publication_pipeline offline-check --site-dir $(SITE_DIR)

check: lint typecheck test build offline-check

serve:
	$(PYTHON) -m mkdocs serve

deploy-local: build
	$(PYTHON) -m publication_pipeline deploy-local \
		--site-dir $(SITE_DIR) \
		--state-root $(LOCAL_STATE_ROOT) \
		--public-path $(LOCAL_PUBLIC_PATH)

preview-local: build
	$(PYTHON) -m publication_pipeline preview-local \
		--site-dir $(SITE_DIR) \
		--state-root $(LOCAL_STATE_ROOT) \
		--public-path $(LOCAL_PUBLIC_PATH) \
		--branch "$${BRANCH:-preview/local}"

rollback-local:
	$(PYTHON) -m publication_pipeline rollback-local \
		--state-root $(LOCAL_STATE_ROOT) \
		--public-path $(LOCAL_PUBLIC_PATH)

benchmark-local:
	$(PYTHON) -m scripts.measure_publication local \
		--runs "$${RUNS:-5}" \
		--run-start "$${RUN_START:-1}"
