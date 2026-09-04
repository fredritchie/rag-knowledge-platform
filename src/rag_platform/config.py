from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfigSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmbeddingSettings(ConfigSection):
    provider: Literal["sentence_transformers", "deterministic"] = "sentence_transformers"
    model: str = "BAAI/bge-small-en-v1.5"
    model_version: str = "bge-small-en-v1.5"
    batch_size: int = Field(32, ge=1)
    dimension: int = Field(384, ge=1)
    normalize: bool = True
    device: str = "cpu"
    query_prefix: str = "Represent this sentence for searching relevant passages: "
    document_prefix: str = ""


class ChunkingSettings(ConfigSection):
    size: int = Field(500, ge=100)
    overlap: int = Field(75, ge=0)
    version: str = "paragraph-char-v2"

    @model_validator(mode="after")
    def validate_overlap(self) -> ChunkingSettings:
        if self.overlap >= self.size:
            raise ValueError("chunking.overlap must be smaller than chunking.size")
        return self


class QdrantSettings(ConfigSection):
    url: str = "http://localhost:6333"
    api_key: str | None = None
    collection: str = "rag_chunks"
    timeout_seconds: float = Field(10.0, gt=0)
    prefer_grpc: bool = False


class RetrievalSettings(ConfigSection):
    mode: Literal["dense", "hybrid", "hybrid_rerank"] = "hybrid_rerank"
    top_k: int = Field(5, ge=1)
    candidate_k: int = Field(20, ge=1)
    similarity_threshold: float | None = Field(0.65, ge=-1, le=1)
    dense_weight: float = Field(0.65, ge=0)
    lexical_weight: float = Field(0.35, ge=0)
    fusion: Literal["weighted", "rrf"] = "rrf"
    rrf_k: int = Field(60, ge=1)


class RerankerSettings(ConfigSection):
    enabled: bool = True
    provider: Literal["sentence_transformers", "none"] = "sentence_transformers"
    model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    model_version: str = "ms-marco-MiniLM-L-6-v2"
    batch_size: int = Field(16, ge=1)
    device: str = "cpu"


class GenerationSettings(ConfigSection):
    provider: Literal["ollama"] = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "llama3.2:3b"
    model_version: str = "llama3.2:3b"
    prompt_version: str = "rag-v1"
    prompt_dir: Path = Path("prompts/rag")
    max_context_tokens: int = Field(4096, ge=128)
    max_output_tokens: int = Field(512, ge=1)
    temperature: float = Field(0.0, ge=0, le=2)
    timeout_seconds: float = Field(120.0, gt=0)
    insufficient_context_message: str = (
        "The available documents do not contain enough information to answer this question."
    )


class SecuritySettings(ConfigSection):
    """RAG safety controls. Tool invocation remains opt-in and disabled by default."""

    tools_enabled: bool = False
    redact_sensitive_data: bool = True
    label_untrusted_documents: bool = True


class EvaluationSettings(ConfigSection):
    retrieval_dataset: Path = Path("evaluation/datasets/retrieval-golden.jsonl")
    rag_dataset: Path = Path("evaluation/datasets/rag-golden.jsonl")
    adversarial_dataset: Path = Path("evaluation/datasets/adversarial.jsonl")
    report_dir: Path = Path("evaluation/reports")
    latency_percentiles: list[int] = [50, 95]


class DatabaseSettings(ConfigSection):
    url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag_platform"
    echo: bool = False
    pool_size: int = Field(10, ge=1)
    max_overflow: int = Field(20, ge=0)
    pool_timeout_seconds: float = Field(30.0, gt=0)


class APISettings(ConfigSection):
    title: str = "RAG Knowledge Platform API"
    version: str = "0.2.0"
    host: str = "127.0.0.1"
    port: int = Field(8080, ge=1, le=65535)
    cors_origins: list[str] = ["http://localhost:3000"]
    request_id_header: str = "X-Request-ID"
    default_page_size: int = Field(25, ge=1, le=200)
    max_page_size: int = Field(100, ge=1, le=500)
    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(120, ge=1)
    rate_limit_window_seconds: int = Field(60, ge=1)


class AuthSettings(ConfigSection):
    enabled: bool = True
    issuer: str = "https://cognito-idp.us-east-1.amazonaws.com/replace-me"
    audience: str = "replace-me-client-id"
    user_pool_id: str | None = None
    jwks_url: str | None = None
    algorithms: list[str] = ["RS256"]
    jwks_cache_seconds: int = Field(3600, ge=1)
    clock_skew_seconds: int = Field(30, ge=0)
    tenant_claim: str = "custom:tenant_id"
    role_claim: str = "cognito:groups"
    group_claim: str = "custom:groups"


class StorageSettings(ConfigSection):
    provider: Literal["s3"] = "s3"
    bucket: str = "replace-me-rag-documents"
    region: str = "us-east-1"
    endpoint_url: str | None = None
    upload_expiry_seconds: int = Field(900, ge=60, le=86400)
    server_side_encryption: Literal["AES256", "aws:kms"] = "AES256"
    kms_key_id: str | None = None


class HealthSettings(ConfigSection):
    check_database: bool = True
    check_qdrant: bool = True
    check_ollama: bool = False
    timeout_seconds: float = Field(2.0, gt=0)


class ObservabilitySettings(ConfigSection):
    enabled: bool = False
    service_name: str = "rag-platform"
    log_level: str = "INFO"
    # Kubernetes must scrape the pod interface; ingress is restricted by NetworkPolicy.
    metrics_host: str = "0.0.0.0"  # nosec B104
    metrics_port: int = Field(9090, ge=1, le=65535)
    otlp_traces_endpoint: str = "http://localhost:4318/v1/traces"
    trace_sample_ratio: float = Field(0.1, ge=0.0, le=1.0)


class WorkerSettings(ConfigSection):
    poll_interval_seconds: float = Field(2.0, gt=0)
    batch_size: int = Field(5, ge=1, le=100)
    max_attempts: int = Field(3, ge=1)
    heartbeat_seconds: int = Field(30, ge=1)


class EventIngestionSettings(ConfigSection):
    enabled: bool = False
    queue_url: str = ""
    dlq_url: str = ""
    wait_time_seconds: int = Field(20, ge=0, le=20)
    visibility_timeout_seconds: int = Field(900, ge=1, le=43200)
    visibility_heartbeat_seconds: int = Field(120, ge=1)
    max_messages: int = Field(5, ge=1, le=10)
    max_receive_count: int = Field(5, ge=1)
    accepted_event_types: list[str] = ["Object Created", "Object Deleted"]
    accepted_prefix: str = "tenants/"
    alarm_on_dlq_messages: bool = True

    @model_validator(mode="after")
    def validate_heartbeat(self) -> EventIngestionSettings:
        if self.visibility_heartbeat_seconds >= self.visibility_timeout_seconds:
            raise ValueError(
                "event_ingestion.visibility_heartbeat_seconds must be smaller than the "
                "visibility timeout"
            )
        return self


class DriveSettings(ConfigSection):
    enabled: bool = False
    sync_interval_seconds: int = Field(300, ge=30)
    page_size: int = Field(100, ge=1, le=1000)
    api_base_url: str = "https://www.googleapis.com/drive/v3"
    upload_base_url: str = "https://www.googleapis.com/upload/drive/v3"
    oauth_token_url: str = "https://oauth2.googleapis.com/token"
    secrets_region: str | None = None
    canonical_prefix: str = "tenants/{tenant_id}/drive/{connection_id}"
    include_shared_drives: bool = True
    allowed_mime_types: list[str] = [
        "application/pdf",
        "application/vnd.google-apps.document",
        "application/vnd.google-apps.presentation",
        "application/vnd.google-apps.spreadsheet",
    ]
    export_mime_types: dict[str, str] = {
        "application/vnd.google-apps.document": "application/pdf",
        "application/vnd.google-apps.presentation": "application/pdf",
        "application/vnd.google-apps.spreadsheet": "application/pdf",
    }


class Settings(ConfigSection):
    data_dir: Path = Path(".rag_data")
    tenant_id: str = "default"
    max_pages: int = Field(1000, ge=1)
    min_avg_chars_per_page: int = Field(40, ge=0)
    max_replacement_char_ratio: float = Field(0.02, ge=0, le=1)
    embedding: EmbeddingSettings = EmbeddingSettings()
    chunking: ChunkingSettings = ChunkingSettings()
    qdrant: QdrantSettings = QdrantSettings()
    retrieval: RetrievalSettings = RetrievalSettings()
    reranker: RerankerSettings = RerankerSettings()
    generation: GenerationSettings = GenerationSettings()
    security: SecuritySettings = SecuritySettings()
    evaluation: EvaluationSettings = EvaluationSettings()
    database: DatabaseSettings = DatabaseSettings()
    api: APISettings = APISettings()
    auth: AuthSettings = AuthSettings()
    storage: StorageSettings = StorageSettings()
    health: HealthSettings = HealthSettings()
    observability: ObservabilitySettings = ObservabilitySettings()
    worker: WorkerSettings = WorkerSettings()
    event_ingestion: EventIngestionSettings = EventIngestionSettings()
    drive: DriveSettings = DriveSettings()

    @property
    def database_path(self) -> Path:
        return self.data_dir / "catalog.sqlite3"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def chunk_size(self) -> int:
        return self.chunking.size

    @property
    def chunk_overlap(self) -> int:
        return self.chunking.overlap

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.documents_dir.mkdir(parents=True, exist_ok=True)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _environment_overrides(prefix: str = "RAG__") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in os.environ.items():
        if not name.startswith(prefix):
            continue
        path = [part.lower() for part in name[len(prefix) :].split("__")]
        target = result
        for part in path[:-1]:
            target = target.setdefault(part, {})
        target[path[-1]] = yaml.safe_load(value)
    if "RAG_DATA_DIR" in os.environ:
        result["data_dir"] = os.environ["RAG_DATA_DIR"]
    return result


def load_settings(path: Path | str | None = None) -> Settings:
    config_path = Path(path or os.getenv("RAG_CONFIG", "config/rag.yaml"))
    raw: dict[str, Any] = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Configuration root must be a mapping: {config_path}")
        raw = loaded
    return Settings.model_validate(_deep_merge(raw, _environment_overrides()))
