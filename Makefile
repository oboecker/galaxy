help: ## This list
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install: ## The Python environment and the viewer's dev dependencies
	cd python && uv sync
	npm install

test: ## The library's tests
	cd python && uv run pytest -q

icons: ## Regenerate viewer/space/icons.js from remixicon
	npm run icons

demo: ## Build the example project into demo/data and serve the demo at http://localhost:8040/demo/
	cd python && uv run python -m galaxy.cli.build --project ../examples/minimal/project.toml \
		--out ../demo/data --procedural --within 5000
	python3 -m http.server 8040 --bind 127.0.0.1

.PHONY: help install test icons demo
