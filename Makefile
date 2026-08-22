.PHONY: install test test-all lint format check corpus clean

install:
	python3 -m pip install -e '.[dev]'

test:
	pytest -m 'not slow'

test-all:
	pytest

lint:
	ruff check src tests

format:
	ruff format src tests
	ruff check --fix src tests

check: lint test

corpus:
	./scripts/download_dev_corpus.sh rag_pdf_corpus

clean:
	rm -rf .rag_data .pytest_cache .ruff_cache htmlcov .coverage
