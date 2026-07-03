
.PHONY: ai-graph test test-e2e test-simulation install-hooks
ai-graph:
	./scripts/graphify-refresh.sh

test:
	pytest

# Browser end-to-end tests (Sprint 11). Requires the e2e extra + browser binaries;
# excluded from `make test` / plain `pytest` by the default "-m not e2e" addopts.
test-e2e:
	pip install -e ".[e2e]"
	playwright install chromium
	pytest tests/e2e -m e2e -v

# Multi-player simulation harness (Sprint 12): real WebSocket clients against a
# live server. No extra install needed (websockets ships with fastapi[standard]);
# excluded from `make test` / plain `pytest` by the default addopts since it spins
# real network servers per test.
test-simulation:
	pytest tests/simulation -m simulation -v

install-hooks:
	git config core.hooksPath .githooks
