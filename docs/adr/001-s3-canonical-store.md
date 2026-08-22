# ADR 001: Amazon S3 as the Canonical Document Store

## Status
Accepted for future cloud phases.

## Decision
All durable source documents will converge on an Amazon S3 canonical store before asynchronous ingestion. Manual uploads write to S3. Google Drive synchronization will copy/update objects in S3 and then reuse the same ingestion pipeline.

## Why
A single canonical source simplifies versioning, replay, checksums, backup, eventing, and recovery. It avoids independent ingestion implementations per connector.

## Phase 0/1 consequence
The local filesystem under `.rag_data/documents/` behaves as a development analogue of the future canonical S3 store.
