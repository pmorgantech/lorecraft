
PYTHON ?= python
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff
BASEDPYRIGHT ?= $(PYTHON) -m basedpyright
PYTEST_WORKERS ?= auto
PYTEST_PARALLEL_ARGS ?= -n $(PYTEST_WORKERS) --dist=loadfile

.PHONY: test test-cov test-e2e test-simulation lint typecheck scripting-docs
ai-graph:
	./scripts/graphify-refresh.sh

# Regenerate the builder-guide scripting vocabulary reference from the live catalog.
# Run this in the SAME commit that changes any scripting registration (register_spec) —
# a CI drift-check (tests/unit/test_scripting_api_doc.py) fails the build if it's stale.
scripting-docs:
	$(PYTHON) -m lorecraft.tools.world_cli vocabulary --out docs/scripting_api.md

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
# Parallelized via pytest-xdist: each worker gets its own browser and server instance.
# Tests are fully isolated (unique tmp_path databases, random ports), so parallel
# execution is safe and ~2.5× faster than serial (31.93s → 12.44s).
test-e2e:
	$(PYTHON) -m pip install -e ".[e2e]"
	$(PYTHON) -m playwright install chromium
	$(PYTEST) tests/e2e -m e2e $(PYTEST_PARALLEL_ARGS) -v

# Multi-player simulation harness (Sprint 12): real WebSocket clients against a
# live server. No extra install needed (websockets ships with fastapi[standard]);
# excluded from `make test` / plain `pytest` by the default addopts since it spins
# real network servers per test.
test-simulation:
	$(PYTEST) tests/simulation -m simulation -v

install-hooks:
	git config core.hooksPath .githooks
