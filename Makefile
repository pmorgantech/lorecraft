
.PHONY: ai-graph test install-hooks
ai-graph:
	./scripts/graphify-refresh.sh

test:
	pytest

install-hooks:
	git config core.hooksPath .githooks
