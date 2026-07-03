
.PHONY: ai-graph test test-e2e install-hooks
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

install-hooks:
	git config core.hooksPath .githooks
