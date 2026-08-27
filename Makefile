.PHONY: install install-ml migrate api ingestion-worker event-worker sync-worker frontend-install frontend-dev test test-all lint format check corpus services-up services-down clean

install:
	python3 -m pip install -e '.[dev]'

install-ml:
	python3 -m pip install -e '.[dev,ml]'

migrate:
	alembic upgrade head

api:
	rag-api

ingestion-worker:
	rag-ingestion-worker

event-worker:
	rag-s3-event-worker

sync-worker:
	rag-sync-worker

frontend-install:
	cd apps/web && npm install

frontend-dev:
	cd apps/web && npm run dev

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

services-up:
	docker compose up -d

services-down:
	docker compose down

clean:
	rm -rf .rag_data .pytest_cache .ruff_cache htmlcov .coverage
