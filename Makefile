
PYTHON ?= python
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff
BASEDPYRIGHT ?= $(PYTHON) -m basedpyright
PYTEST_WORKERS ?= auto
PYTEST_PARALLEL_ARGS ?= -n $(PYTEST_WORKERS) --dist=loadfile

.PHONY: test test-cov test-e2e test-simulation lint typecheck
ai-graph:
	./scripts/graphify-refresh.sh

test:
	$(PYTEST) $(PYTEST_PARALLEL_ARGS)

# Sprint 13 CI gate: default suite with a coverage threshold (fails under the
# [tool.coverage.report] fail_under in pyproject.toml). Requires the dev extra
# (pytest-cov + pytest-xdist). pytest-cov combines worker coverage under xdist.
test-cov:
	$(PYTEST) $(PYTEST_PARALLEL_ARGS) --cov=src/lorecraft --cov-report=term-missing

lint:
	$(RUFF) check .
	$(RUFF) format --check .

typecheck:
	$(BASEDPYRIGHT)

# Browser end-to-end tests (Sprint 11). Requires the e2e extra + browser binaries;
# excluded from `make test` / plain `pytest` by the default "-m not e2e" addopts.
test-e2e:
	$(PYTHON) -m pip install -e ".[e2e]"
	$(PYTHON) -m playwright install chromium
	$(PYTEST) tests/e2e -m e2e -v

# Multi-player simulation harness (Sprint 12): real WebSocket clients against a
# live server. No extra install needed (websockets ships with fastapi[standard]);
# excluded from `make test` / plain `pytest` by the default addopts since it spins
# real network servers per test.
test-simulation:
	$(PYTEST) tests/simulation -m simulation -v

install-hooks:
	git config core.hooksPath .githooks
