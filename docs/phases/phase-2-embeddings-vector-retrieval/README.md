# Phase 2 — Embeddings and Basic Vector Retrieval

## 1. Purpose

Phase 2 proves that previously ingested PDF chunks can be embedded, stored in Qdrant, and
retrieved by semantic similarity. It deliberately separates ingestion from indexing so that
embedding model changes and index rebuilds are explicit operations.

The Phase 2 proof should be run in `dense` retrieval mode. Hybrid retrieval and reranking are
implemented as Phase 4 extensions and are the repository defaults, but they must be disabled
when measuring the dense-only Phase 2 baseline.

## 2. Exit criterion

Phase 2 is accepted when all of the following are true:

- Valid ingested documents have deterministic, page-aware chunks in SQLite.
- Every selected chunk is embedded with the configured embedding model.
- Every vector is stored in the configured Qdrant collection with the required payload.
- Queries are embedded with the same model family and vector dimension.
- Search is tenant-scoped and returns page-aware chunk metadata.
- A corpus-specific golden set achieves an intentionally selected Hit@K/MRR target consistently.
- Retrieval latency is recorded and is acceptable for the development environment.
- The result can be inspected from the CLI or developer web interface without an LLM.

No language model is needed to satisfy Phase 2.

## 3. Implemented data flow

Indexing:

```text
SQLite chunks
    │
    ├─ verify document exists and belongs to configured tenant
    ├─ transition document to EMBEDDING
    ├─ embed chunks in configured batches
    ├─ transition document to INDEXING
    ├─ ensure Qdrant collection and payload indexes exist
    ├─ upsert vector points in batches
    ├─ transition document to VALIDATING
    └─ transition document to ACTIVE
```

Dense querying:

```text
Question
    │
    ├─ apply configured query prefix
    ├─ generate normalized query vector
    ├─ Qdrant cosine search with tenant filter and threshold
    ├─ resolve authoritative chunk text from SQLite
    └─ return top-K SearchResult records and latency
```

The authoritative text catalog remains SQLite. Qdrant also carries text in its payload for
inspection, but search results are reconstructed from SQLite using returned `chunk_id` values.
This prevents a stale or malformed vector payload from becoming the canonical document record.

## 4. Relevant source files

| Responsibility | File |
|---|---|
| Typed configuration and validation | `src/rag_platform/config.py` |
| Chunk and search response models | `src/rag_platform/domain/models.py` |
| Embedding provider interface | `src/rag_platform/retrieval/embeddings.py` |
| Qdrant and in-memory vector stores | `src/rag_platform/retrieval/vector_store.py` |
| Indexing and retrieval orchestration | `src/rag_platform/retrieval/service.py` |
| SQLite chunk/document catalog | `src/rag_platform/storage/sqlite.py` |
| Developer CLI | `src/rag_platform/cli.py` |
| Developer HTTP/UI surface | `src/rag_platform/web.py` |
| Runtime defaults | `config/rag.yaml` |

`InMemoryVectorStore` and `DeterministicEmbedder` exist for tests and plumbing checks. The
deterministic embedder hashes tokens; it does not provide production-quality semantic meaning.

## 5. Prerequisites

### 5.1 Python environment

Install application, test, embedding, and reranking dependencies:

```bash
make install-ml
```

The ML extra installs `sentence-transformers`. The base install intentionally does not install
the model runtime because it is comparatively large.

### 5.2 Qdrant

Start the configured external services:

```bash
make services-up
```

The default Qdrant URL is `http://localhost:6333`. Docker is not required by the Python code, but
some reachable Qdrant instance is required for the default vector-store implementation.

Check service reachability:

```bash
curl http://localhost:6333/healthz
```

### 5.3 Ingested documents

Phase 2 indexes chunks already created by ingestion:

```bash
ragctl ingest ./path/to/document.pdf
ragctl list
ragctl chunks doc_xxxxxxxxxxxxxxxxxxxx --page 1
```

Ingestion reads `chunking.size`, `chunking.overlap`, and `chunking.version` from the shared YAML
configuration unless command-line chunk overrides are supplied.

## 6. Complete Phase 2 configuration

```yaml
data_dir: .rag_data
tenant_id: default

embedding:
  provider: sentence_transformers
  model: BAAI/bge-small-en-v1.5
  model_version: bge-small-en-v1.5
  batch_size: 32
  dimension: 384
  normalize: true
  device: cpu
  query_prefix: "Represent this sentence for searching relevant passages: "
  document_prefix: ""

chunking:
  size: 500
  overlap: 75
  version: paragraph-char-v2

qdrant:
  url: http://localhost:6333
  api_key: null
  collection: rag_chunks
  timeout_seconds: 10
  prefer_grpc: false

retrieval:
  mode: dense
  top_k: 5
  candidate_k: 20
  similarity_threshold: 0.65
```

### 6.1 Embedding fields

| Field | Meaning | Operational consequence |
|---|---|---|
| `provider` | Embedder implementation | `sentence_transformers` is semantic; `deterministic` is test-only. |
| `model` | Model registry/name passed to Sentence Transformers | May cause a model download on first use. |
| `model_version` | Version label stored in payload and responses | Change it whenever weights or embedding behavior change. |
| `batch_size` | Chunks encoded per model call and points upserted per request | Larger values improve throughput but consume more memory. |
| `dimension` | Expected vector size | Must equal the loaded model dimension and Qdrant collection dimension. |
| `normalize` | Whether embeddings are L2-normalized | Enabled for cosine retrieval consistency. |
| `device` | Sentence Transformers device | Typical values are `cpu`, `cuda`, or `mps`, subject to runtime support. |
| `query_prefix` | Text prepended only to queries | BGE retrieval instructions can materially affect recall. |
| `document_prefix` | Text prepended only to chunks | Empty for the configured BGE model. |

The embedder checks the loaded model dimension against `embedding.dimension` and fails before
indexing if they differ.

### 6.2 Chunking fields

`size` and `overlap` are character counts, not tokenizer counts. `size` must be at least 100.
`overlap` must be non-negative and strictly less than `size`. Chunks never cross PDF page
boundaries, which makes every citation unambiguously page-level.

Changing chunking settings does not rewrite existing chunks. Re-ingest into a clean data
directory or deliberately rebuild the affected document records before comparing chunk sizes.

### 6.3 Qdrant fields

`url`, `api_key`, timeout, transport preference, and collection name are externalized. On first
indexing, the code creates a cosine-distance collection and keyword payload indexes for
`tenant_id` and `document_id`.

If an existing collection has a different vector dimension, indexing fails with instructions to
use a new collection or recreate the old one. It does not silently destroy a collection.

### 6.4 Retrieval fields used by dense mode

- `top_k` is the number of results returned to the caller.
- `candidate_k` is the candidate pool size. The service uses at least `top_k` even if
  `candidate_k` is configured lower.
- `similarity_threshold` is passed to Qdrant as the dense score threshold. Set it to `null` to
  disable thresholding. Raising it increases precision and unsupported-query rejection but can
  reduce recall.

### 6.5 Environment overrides

Every setting can be overridden without changing Python or YAML:

```bash
export RAG__EMBEDDING__BATCH_SIZE=64
export RAG__EMBEDDING__DEVICE=mps
export RAG__QDRANT__COLLECTION=rag_chunks_bge_v2
export RAG__RETRIEVAL__MODE=dense
export RAG__RETRIEVAL__TOP_K=5
export RAG__RETRIEVAL__SIMILARITY_THRESHOLD=0.65
ragctl config-show
```

Environment values are YAML-decoded, so numbers, booleans, `null`, and lists retain their types.
`RAG_CONFIG` can select a different configuration file. The legacy `RAG_DATA_DIR` override is
also supported.

## 7. Indexing behavior in detail

### 7.1 Single-document indexing

```bash
ragctl index doc_xxxxxxxxxxxxxxxxxxxx
```

The operation:

1. Reads the document from SQLite.
2. Rejects a missing document or a document owned by a different configured tenant.
3. Loads all chunks for the document in deterministic `chunk_index` order.
4. Validates the document lifecycle transition to `EMBEDDING`.
5. Encodes chunks in `embedding.batch_size` batches.
6. Builds Qdrant points in memory.
7. Marks the document `FAILED_EMBEDDING` if encoding fails.
8. Transitions to `INDEXING` after all vectors exist.
9. Ensures the Qdrant collection has the correct dimension.
10. Upserts points in the same configured batch size.
11. Marks the document `FAILED_INDEXING` if Qdrant creation or upsert fails.
12. Transitions through `VALIDATING` to `ACTIVE` on success.

Documents in `ACTIVE`, `FAILED_EMBEDDING`, or `FAILED_INDEXING` can be retried. Point upserts are
idempotent because a chunk always maps to the same deterministic Qdrant point UUID.

### 7.2 Bulk indexing

```bash
ragctl index --all
```

Only documents owned by the configured tenant and in an indexable/retryable status are selected.
Bulk indexing is sequential. The first unhandled document failure stops the command; successful
documents indexed earlier remain indexed.

### 7.3 Qdrant point identity

Chunk IDs are strings such as `chk_<24 hex characters>`. Qdrant point IDs are UUIDv5 values
derived from the chunk ID and `uuid.NAMESPACE_URL`. The original chunk ID is preserved in the
payload as `chunk_id` and is used to join results back to SQLite.

### 7.4 Qdrant payload contract

Each point stores:

```json
{
  "chunk_id": "chk_...",
  "tenant_id": "default",
  "document_id": "doc_...",
  "document_version": 1,
  "source": "manual",
  "page": 4,
  "filename": "NIST-SP-800-207.pdf",
  "chunk_index": 12,
  "embedding_model_version": "bge-small-en-v1.5",
  "chunker_version": "paragraph-char-v2",
  "text": "..."
}
```

`page` is one-based because it comes from PDF extraction. `chunk_index` is document-global;
`page_chunk_index` remains available in SQLite but is not currently duplicated into Qdrant.

## 8. Search behavior in detail

Run a dense-only search:

```bash
ragctl search "What is zero trust?" --mode dense
ragctl search "What is zero trust?" --mode dense --top-k 5 --json
```

The result object contains:

```json
{
  "chunk_id": "chk_...",
  "tenant_id": "default",
  "document_id": "doc_...",
  "document_version": 1,
  "source": "manual",
  "page": 4,
  "filename": "NIST-SP-800-207.pdf",
  "chunk_index": 12,
  "embedding_model_version": "bge-small-en-v1.5",
  "chunker_version": "paragraph-char-v2",
  "text": "...",
  "score": 0.89,
  "dense_score": 0.89,
  "lexical_score": null,
  "reranker_score": null
}
```

Qdrant always receives a `tenant_id` match filter. SQLite chunk resolution also receives the
same tenant filter. Missing or stale Qdrant chunk IDs are omitted rather than returned with
payload-only text.

The service records the most recent stage timings in `RetrievalService.last_metrics`:

- `embedding_latency_ms`
- `dense_latency_ms`
- `lexical_latency_ms`
- `fusion_latency_ms`
- `reranker_latency_ms`
- `retrieval_latency_ms`

In dense mode, lexical, fusion, and reranker latency are zero.

## 9. Developer search interface

Start the web app:

```bash
ragctl serve --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The temporary UI displays rank, filename, page, score, chunk ID,
text, result count, and total retrieval latency.

The JSON endpoint is:

```bash
curl -X POST http://127.0.0.1:8000/api/search \
  -H 'content-type: application/json' \
  -d '{"query":"What is zero trust?","top_k":5}'
```

This is a developer interface. It has no authentication or public API stability guarantee and
must not be exposed directly to untrusted networks.

## 10. De-indexing and deletion

Vector deletion and catalog deletion are separate explicit operations:

```bash
ragctl deindex doc_xxxxxxxxxxxxxxxxxxxx
ragctl delete doc_xxxxxxxxxxxxxxxxxxxx
```

`deindex` deletes points matching both `document_id` and configured `tenant_id`. `delete` removes
local chunks, soft-deletes the document record, and removes the stored PDF unless `--keep-file`
is provided. Running only `delete` leaves Qdrant points behind, although stale IDs are omitted
when SQLite cannot resolve them. Use both commands for proper data retention behavior.

## 11. Phase 2 evaluation dataset

Populate `evaluation/datasets/retrieval-golden.jsonl` with questions whose correct source is
already known:

```json
{"question":"What is zero trust?","expected_document":"NIST-SP-800-207.pdf","expected_pages":[4],"should_answer":true}
```

`expected_document` can match a document ID, full filename, or filename stem. If
`expected_pages` is empty, any page in the expected document counts. If pages are supplied, both
the document and one of those pages must match.

Run the baseline:

```bash
RAG__RETRIEVAL__MODE=dense ragctl evaluate retrieval --report-name phase2-dense
```

The evaluator always requests five results because it computes Hit@1, Hit@3, and Hit@5.

## 12. Failure modes and troubleshooting

### `sentence-transformers is required`

Run `make install-ml`. Do not switch to the deterministic provider for a semantic quality test.

### Model dimension mismatch

Ensure `embedding.dimension` matches the actual model. BGE small English v1.5 emits 384
dimensions. When changing dimension, select a new Qdrant collection name or deliberately
recreate the old collection.

### Qdrant connection refused

Confirm `qdrant.url`, service health, port mapping, firewall, API key, and timeout. Indexing will
move a document to `FAILED_INDEXING`; rerun indexing after correcting the service.

### No results

Check, in order:

1. The document exists under the configured `data_dir` and `tenant_id`.
2. Indexing completed and the document returned to `ACTIVE`.
3. Query and document embeddings use the same model and prefixes.
4. Qdrant collection and configured collection name match.
5. `similarity_threshold` is not too high.
6. The expected content survived extraction and appears in `ragctl chunks`.

### Unexpectedly weak semantic results

Verify that evaluation is using `sentence_transformers`, not `deterministic`; inspect chunk
boundaries; confirm BGE query instructions; and compare thresholds on a sufficiently large,
representative golden set rather than one question.

## 13. Tests

`tests/test_phase2_4.py` verifies configuration overrides, vector payload contents, indexing,
tenant metadata, hybrid plumbing, citations, persistence, and retrieval metrics using offline
test providers. Existing ingestion tests verify page-preserving deterministic chunks.

Run:

```bash
make check
```

Offline tests prove orchestration and contracts. They do not prove the quality of BGE weights or
the availability/performance of an external Qdrant deployment; the golden-set run does that.

## 14. Acceptance checklist

- [ ] `ragctl config-show` displays the intended model, dimension, tenant, collection, and dense mode.
- [ ] The expected corpus is ingested with the intended chunk configuration.
- [ ] Qdrant is healthy and uses the expected collection.
- [ ] `ragctl index --all` completes without failed document states.
- [ ] A Qdrant point inspection shows every required payload field.
- [ ] Dense CLI search returns the expected filename and page for known questions.
- [ ] The developer UI shows the same result ordering as the CLI.
- [ ] The retrieval golden set contains representative semantic and exact-term questions.
- [ ] Hit@1, Hit@3, Hit@5, MRR, mean latency, p50, and p95 are recorded.
- [ ] The chosen threshold is justified by measured recall and unsupported-query behavior.
- [ ] Repeated runs are stable enough to satisfy the agreed development target.
