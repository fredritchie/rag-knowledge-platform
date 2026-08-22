# ADR 002: Qdrant for Vector Retrieval

## Status
Accepted for Phase 2+, not implemented in Phase 0/1.

## Decision
Use Qdrant for dense vector retrieval with metadata payload filters.

## Key requirement
Tenant and document authorization filters must be applied during retrieval so unauthorized chunks never enter the prompt context.

## Phase 0/1 consequence
Chunks already contain stable document/page/version/checksum metadata so Qdrant payload construction can be added without redesigning the parser.
