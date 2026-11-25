help: ## This list
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install: ## The Python environment and the viewer's dev dependencies
	cd python && uv sync
	npm install

test: ## The library's tests
	cd python && uv run pytest -q

icons: ## Regenerate viewer/space/icons.js from remixicon
	npm run icons

.PHONY: help install test icons
