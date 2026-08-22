from __future__ import annotations

from rag_platform.domain.states import DocumentStatus

_ALLOWED: dict[DocumentStatus, set[DocumentStatus]] = {
    DocumentStatus.RECEIVED: {
        DocumentStatus.DOWNLOADING,
        DocumentStatus.PARSING,
        DocumentStatus.FAILED_DOWNLOAD,
        DocumentStatus.FAILED_PARSE,
        DocumentStatus.DELETING,
    },
    DocumentStatus.DOWNLOADING: {
        DocumentStatus.PARSING,
        DocumentStatus.FAILED_DOWNLOAD,
        DocumentStatus.DELETING,
    },
    DocumentStatus.PARSING: {
        DocumentStatus.CHUNKING,
        DocumentStatus.FAILED_PARSE,
        DocumentStatus.DELETING,
    },
    DocumentStatus.CHUNKING: {
        DocumentStatus.EMBEDDING,
        DocumentStatus.VALIDATING,
        DocumentStatus.FAILED_PARSE,
        DocumentStatus.DELETING,
    },
    # Phase 1 stops before embeddings/indexing. These transitions are defined now for later phases.
    DocumentStatus.EMBEDDING: {
        DocumentStatus.INDEXING,
        DocumentStatus.FAILED_EMBEDDING,
        DocumentStatus.DELETING,
    },
    DocumentStatus.INDEXING: {
        DocumentStatus.VALIDATING,
        DocumentStatus.FAILED_INDEXING,
        DocumentStatus.DELETING,
    },
    DocumentStatus.VALIDATING: {
        DocumentStatus.ACTIVE,
        DocumentStatus.FAILED_VALIDATION,
        DocumentStatus.DELETING,
    },
    DocumentStatus.ACTIVE: {DocumentStatus.DELETING},
    DocumentStatus.FAILED_DOWNLOAD: {DocumentStatus.DELETING},
    DocumentStatus.FAILED_PARSE: {DocumentStatus.DELETING},
    DocumentStatus.FAILED_EMBEDDING: {DocumentStatus.DELETING},
    DocumentStatus.FAILED_INDEXING: {DocumentStatus.DELETING},
    DocumentStatus.FAILED_VALIDATION: {DocumentStatus.DELETING},
    DocumentStatus.DELETING: {DocumentStatus.DELETED},
    DocumentStatus.DELETED: set(),
}


class InvalidStatusTransition(ValueError):
    pass


def ensure_transition(current: DocumentStatus, target: DocumentStatus) -> None:
    if target not in _ALLOWED[current]:
        raise InvalidStatusTransition(f"Invalid document transition: {current} -> {target}")
