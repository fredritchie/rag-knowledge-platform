# ADR 003: PostgreSQL for Application Metadata

## Status
Accepted for application/cloud phases.

## Decision
Use PostgreSQL for tenants, users/application profiles, document metadata, versions, ACLs, ingestion jobs, synchronization cursors, audits, chats, prompts, and lineage.

## Phase 0/1 consequence
SQLite is used only as a local development catalog. Its schema is intentionally relational so migration to PostgreSQL is straightforward.
