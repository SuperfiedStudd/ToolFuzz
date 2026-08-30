PYTHON ?= python3

.PHONY: install test regression lint docker-build docker-test

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest -q

regression:
	$(PYTHON) -m toolfuzz.cli run examples/refund_agent/scenarios/

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

docker-build:
	docker build -t toolfuzz .

docker-test: docker-build
	docker run --rm toolfuzz run examples/refund_agent/scenarios/
