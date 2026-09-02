# syntax=docker/dockerfile:1.7
ARG OLLAMA_IMAGE=ollama/ollama:0.33.2@sha256:020e4134285e2ef4d8fd801234176de3b4faadc992a3eb06c8e66a2f9d4c4ba2

FROM ${OLLAMA_IMAGE} AS verify
RUN ollama --version

FROM verify AS runtime
ARG APP_VERSION=0.33.2
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="RAG Platform Ollama runtime" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}"
ENV HOME=/home/ollama \
    OLLAMA_HOST=0.0.0.0:11434 \
    OLLAMA_MODELS=/models
USER root
RUN mkdir -p /home/ollama /models \
    && chown -R 10001:10001 /home/ollama /models
USER 10001:10001
EXPOSE 11434
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["ollama", "list"]
ENTRYPOINT ["ollama"]
CMD ["serve"]
