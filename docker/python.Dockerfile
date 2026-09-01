# syntax=docker/dockerfile:1.7
ARG PYTHON_IMAGE=python:3.12.11-slim-bookworm

FROM ${PYTHON_IMAGE} AS source
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /src
COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY tests ./tests
COPY migrations ./migrations
COPY config ./config
COPY prompts ./prompts

FROM source AS test
RUN python -m pip install --no-cache-dir '.[dev]' \
    && ruff check src tests \
    && pytest -m 'not slow'

FROM test AS build
RUN python -m pip wheel --wheel-dir /wheels .

FROM ${PYTHON_IMAGE} AS runtime
ARG APP_VERSION=dev
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="RAG Platform Python runtime" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/replace-me/production-rag-knowledge-platform"
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RAG_CONFIG=/app/config/rag.yaml \
    RAG_DATA_DIR=/var/lib/rag
RUN groupadd --gid 10001 rag \
    && useradd --uid 10001 --gid rag --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin rag \
    && python -m venv /opt/venv \
    && mkdir -p /app /var/lib/rag \
    && chown -R rag:rag /app /var/lib/rag /opt/venv
COPY --from=build --chown=rag:rag /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels production-rag-knowledge-platform \
    && rm -rf /wheels
WORKDIR /app
COPY --from=source --chown=rag:rag /src/alembic.ini ./alembic.ini
COPY --from=source --chown=rag:rag /src/migrations ./migrations
COPY --from=source --chown=rag:rag /src/config ./config
COPY --from=source --chown=rag:rag /src/prompts ./prompts
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os; os.kill(1, 0)"]
CMD ["rag-api"]

