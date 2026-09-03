# Phase 1 — Development Dataset and PDF Processing Foundation

## 1. Purpose

Phase 1 establishes a deterministic, inspectable PDF-processing foundation before embeddings,
retrieval, or generation are allowed to influence the system. Its job is to turn a deliberately
varied 50-PDF development corpus into validated document records and page-aware chunks, while
classifying bad inputs explicitly.

Retrieval quality cannot compensate for corrupt files, missing text, unstable chunk boundaries,
lost page numbers, or silent duplicate ingestion. Phase 1 makes those conditions visible and
testable.

## 2. Objective

Build a local processing layer that can:

- Validate a file before treating it as a PDF.
- Extract PDF metadata and text predictably.
- Preserve physical one-based PDF page numbers.
- Normalize common extraction artifacts without flattening paragraphs.
- Produce deterministic, overlapping, page-bounded chunks.
- Persist document, chunk, validation-issue, and file-location metadata.
- Detect and classify known bad-document conditions.
- Support developer inspection and deletion through **ragctl**.
- Process the corpus progressively at 10-, 20-, and 50-document gates.

No embedding model, vector database, reranker, or LLM is required to complete Phase 1.

## 3. Exit criterion

Phase 1 is accepted when all 50 development PDFs have been attempted deterministically and:

- Every successful document is **ACTIVE** with persisted page-aware chunks.
- Every rejected document has an explicit machine-readable issue classification.
- Repeated chunking with the same document ID, pages, and configuration produces the same IDs.
- Physical page numbers can be traced from chunks to original PDFs.
- Duplicate content is rejected within the configured tenant.
- Canonical PDF copies and catalog records can be inspected and deleted.
- Expected exceptions are documented instead of silently omitted.

“All 50 can be processed” means every file produces either a valid active result or an intentional,
well-classified rejection. It does not mean every real-world PDF must be forced into **ACTIVE**.

## 4. Staged corpus rollout

Do not begin with all 50 documents:

~~~text
First 10 PDFs
      │
      ├─ validate downloads and ingestion
      ├─ inspect metadata and chunks
      └─ resolve unexpected failures
             │
         First 20 PDFs
             │
             ├─ repeat validation
             ├─ compare counts and warnings
             └─ inspect broader variation
                    │
                All 50 PDFs
                    │
                    ├─ standards and exact IDs
                    ├─ related documents
                    ├─ long reports/manuals
                    ├─ tables and diagrams
                    └─ final acceptance evidence
~~~

The staged process limits the debugging surface. If the first ten fail, adding forty more usually
hides the root cause behind additional output.

### 4.1 Gate 1: first 10

The first ten manifest entries are AI/RAG research papers. They exercise equations, figures,
academic layouts, citations, and core retrieval terminology.

~~~bash
rm -rf .rag_data_gate10
ragctl ingest-dir rag_pdf_corpus --limit 10 --data-dir .rag_data_gate10
ragctl list --data-dir .rag_data_gate10
~~~

Before advancing:

- Confirm the expected ten files were selected.
- Inspect every status.
- Inspect first, middle, and last pages from multiple documents.
- Confirm global chunk indices are sequential and pages are plausible.
- Record low-density warnings and decide whether they are expected.

### 4.2 Gate 2: first 20

The first twenty introduce surveys, evaluation papers, longer model reports, conversion work,
GPU terminology, and more complex tables.

~~~bash
rm -rf .rag_data_gate20
ragctl ingest-dir rag_pdf_corpus --limit 20 --data-dir .rag_data_gate20
ragctl list --data-dir .rag_data_gate20
~~~

Use a clean data directory for each comparison. Continuing in gate 10 reports those ten files as
duplicates, which is useful for duplicate testing but noisy for a clean gate run.

### 4.3 Gate 3: all 50

~~~bash
rm -rf .rag_data_gate50
ragctl ingest-dir rag_pdf_corpus --limit 50 --data-dir .rag_data_gate50
ragctl list --data-dir .rag_data_gate50
~~~

The final gate adds security standards, related HTTP/QUIC RFCs, handbooks, statistical reports,
architecture guidance, exact control identifiers, tables, figures, and very long documents.

### 4.4 File-selection semantics

**ingest-dir** recursively finds files ending in **.pdf**, sorts paths lexicographically, and then
applies the limit. With the repository category names, the first 10 and 20 are the AI/RAG files.
If directory layout changes, verify selected paths rather than assuming the limit still follows
manifest order.

## 5. Corpus design

The curated manifest contains 50 PDFs:

| Category | Range | Processing value |
|---|---:|---|
| AI/RAG | 1–20 | Papers, equations, figures, tables, surveys, similar terminology. |
| Security standards | 21–30 | NIST identifiers, controls, checklists, diagrams. |
| Networking RFCs | 31–40 | Exact protocol syntax and related standards. |
| Reports/manuals | 41–50 | Handbooks, charts, tables, domain shifts, diagrams. |

It intentionally contains:

- Short and long PDFs.
- Technical and non-technical domains.
- Table-heavy and diagram-heavy pages.
- Closely related documents that are easy to confuse.
- Standards containing exact identifiers.
- Multi-column papers and reference-heavy documents.
- Documents near or beyond page-count policy limits.
- Visual content that exposes text-only extraction limits.

The catalog is [datasets/manifest.csv](../../../datasets/manifest.csv). The downloader currently
reads **scripts/manifest.csv**; keep the two manifests synchronized when editing the corpus.

## 6. Downloading the corpus

~~~bash
make corpus
~~~

Equivalent:

~~~bash
./scripts/download_dev_corpus.sh rag_pdf_corpus
~~~

The script:

1. Creates category directories and **rag_pdf_corpus/failed**.
2. Requires curl.
3. Reads CSV safely with Python's CSV parser.
4. Downloads to a temporary **.part** path.
5. Uses redirects, retries, connection/total timeouts, and a custom user agent.
6. Checks the first five bytes for **%PDF-**.
7. Moves valid-looking responses into the category directory.
8. Moves non-PDF responses into **failed** with an **.invalid** suffix.
9. Records failed URLs in **failed_downloads.tsv**.

This signature check is only transport sanity. **ragctl validate** still performs authoritative
parser and quality validation.

Downloaded PDFs are ignored by Git. External URLs can change, redirect, rate-limit, or disappear;
preserve corpus checksums for long-lived reproducibility.

~~~bash
find rag_pdf_corpus -type f -name '*.pdf' | wc -l
find rag_pdf_corpus/failed -maxdepth 1 -type f -print
~~~

## 7. Implemented processing pipeline

~~~text
PDF path
   │
   ├─ path and regular-file validation
   ├─ non-zero file-size validation
   ├─ %PDF- signature validation
   ├─ streaming SHA-256 checksum
   ├─ PyMuPDF parser open
   ├─ password/page-count checks
   ├─ PDF metadata extraction
   ├─ page-by-page text extraction
   ├─ extracted-text quality assessment
   ├─ per-page Unicode/whitespace cleaning
   ├─ page-bounded overlapping chunking
   ├─ SQLite persistence
   ├─ canonical local PDF copy
   └─ ACTIVE or classified failure
~~~

Validation and ingestion share preflight and text-quality logic. **validate** does not add a
document record; **ingest** persists lifecycle state, issues, chunks, and a PDF copy.

## 8. Relevant source files

| Responsibility | File |
|---|---|
| Configuration | **src/rag_platform/config.py**, **config/rag.yaml** |
| File preflight/hashing | **src/rag_platform/ingestion/validator.py** |
| Page-aware extraction | **src/rag_platform/ingestion/extractor.py** |
| Text normalization | **src/rag_platform/ingestion/cleaner.py** |
| Text-quality checks | **src/rag_platform/ingestion/quality.py** |
| Deterministic chunking | **src/rag_platform/ingestion/chunker.py** |
| Pipeline orchestration | **src/rag_platform/ingestion/service.py** |
| Models and states | **src/rag_platform/domain/models.py**, **states.py** |
| Lifecycle validation | **src/rag_platform/domain/state_machine.py** |
| SQLite persistence | **src/rag_platform/storage/sqlite.py** |
| Developer CLI | **src/rag_platform/cli.py** |
| Corpus/downloader | **datasets/manifest.csv**, **scripts/download_dev_corpus.sh** |
| Fixtures/tests | **tests/conftest.py**, **tests/test_validation.py** |

## 9. Configuration

~~~yaml
data_dir: .rag_data
tenant_id: default
max_pages: 1000
min_avg_chars_per_page: 40
max_replacement_char_ratio: 0.02

chunking:
  size: 500
  overlap: 75
  version: paragraph-char-v2
~~~

| Field | Constraint | Meaning |
|---|---|---|
| **data_dir** | path | Root for SQLite and canonical copies. |
| **tenant_id** | string | Ownership scope on documents/chunks. |
| **max_pages** | integer ≥ 1 | PDFs above this physical count fail. |
| **min_avg_chars_per_page** | integer ≥ 0 | Low-density warning threshold. |
| **max_replacement_char_ratio** | 0–1 | Encoding-error threshold. |
| **chunking.size** | integer ≥ 100 | Proposed cleaned-character window. |
| **chunking.overlap** | 0 ≤ overlap < size | Adjacent per-page overlap. |
| **chunking.version** | string | Persisted processing label. |

Repository defaults are 500/75. The lower-level **ChunkingConfig** constructor retains 1200/200
defaults, but normal CLI ingestion passes shared application settings explicitly.

Overrides:

~~~bash
export RAG__MAX_PAGES=600
export RAG__MIN_AVG_CHARS_PER_PAGE=25
export RAG__MAX_REPLACEMENT_CHAR_RATIO=0.01
export RAG__CHUNKING__SIZE=800
export RAG__CHUNKING__OVERLAP=100
export RAG__CHUNKING__VERSION=paragraph-char-c800-v1
ragctl config-show
~~~

**RAG_CONFIG** chooses another YAML file. **RAG_DATA_DIR** remains a legacy override. Explicit
**--data-dir** wins for a command. Single-file ingestion also supports **--chunk-size** and
**--chunk-overlap**.

## 10. Preflight validation in exact order

### 10.1 Path and file

- Missing path → **NOT_FOUND**.
- Existing non-file path → **NOT_A_FILE**.
- Zero-byte file → **EMPTY_PDF**.

Each is an error and stops further work.

### 10.2 Signature

The first five bytes must equal **%PDF-**. A mismatch produces **NOT_PDF** and records observed
signature bytes in hexadecimal. This blocks obvious HTML/text downloads but does not prove the PDF
structure is valid.

### 10.3 Checksum

Files with a valid signature are SHA-256 hashed in 1 MiB blocks, avoiding full-file memory loading.
The full lowercase digest becomes content identity.

### 10.4 Parser and encryption

PyMuPDF opens the document. Parser exceptions become **CORRUPTED_PDF** with the parser error.
**needs_pass** produces **PASSWORD_PROTECTED**. Phase 1 accepts no passwords.

### 10.5 Page count

- Zero parsed pages → **EMPTY_PDF**.
- Page count greater than **max_pages** → **EXCESSIVE_PAGE_COUNT**.
- Count equal to the maximum is accepted.

Actual and configured counts are stored in issue details.

### 10.6 PDF metadata

Preflight extracts optional title, author, subject, and keywords. Empty values become null.
Metadata is untrusted display information, never content identity.

## 11. Duplicate detection

Ingestion hashes a non-empty regular file before parsing and asks SQLite for a non-deleted record
with the same checksum and tenant.

- Identity is content-based, not filename-based.
- Renaming identical bytes does not avoid detection.
- Detection is tenant-scoped.
- Soft-deleted records are excluded.
- Re-ingestion after deletion creates a new random document ID.
- **DUPLICATE_DOCUMENT** exists as an issue enum, but current duplicate attempts raise
  **DuplicateDocumentError** before creating a new issue record.

CLI duplicate exit code is 3.

## 12. Text extraction

**extract_pages** opens the PDF and calls **page.get_text("text", sort=True)** for each page.
Missing text becomes an empty string. Every result has:

- **page_number**: one-based physical PDF page index.
- **text**: raw extracted page text.

Physical page 1 may not match printed label “i”, “1”, or “A-1”. Persisted citations always use the
physical index.

Not currently extracted:

- OCR from images.
- Structured table cells.
- Diagram meaning.
- Bounding boxes/font styles/headings.
- Layout coordinates or richer reading-order correction.

## 13. Text-quality assessment

All raw pages are concatenated for quality calculations.

### Useful characters

**extracted_characters** counts non-whitespace characters. Density is useful characters divided by
extracted page count.

### Zero text

Zero useful characters produces **ZERO_EXTRACTED_TEXT** as an error and notes OCR may be needed.

### Low density

Average below **min_avg_chars_per_page** produces **LOW_TEXT_DENSITY** as a warning. It does not
block activation because diagram-heavy, sparse, or short documents may still be useful.

### Unsupported encoding

The ratio of Unicode replacement characters U+FFFD to all raw extracted characters is calculated.
A ratio strictly greater than **max_replacement_char_ratio** produces **UNSUPPORTED_ENCODING**.

### Extraction exceptions

Page-extraction exceptions become **EXTRACTION_ERROR**, persist their error string, and move the
document to **FAILED_PARSE**.

## 14. Text cleaning

Cleaning occurs independently per page:

1. Unicode NFKC normalization.
2. CRLF/bare-CR conversion to newline.
3. Removal of hyphen-newline between word characters.
4. Single line-break conversion to a space.
5. Repeated spaces/tabs collapsed.
6. Three or more newlines collapsed to two.
7. Leading/trailing whitespace stripped.

Example:

~~~text
retriev-
al system
with   spaces


second paragraph
~~~

becomes:

~~~text
retrieval system with spaces

second paragraph
~~~

Paragraphs survive as double newlines. The cleaner does not remove headers, footers, page numbers,
references, repeated captions, or boilerplate.

## 15. Chunking algorithm

Chunking is deterministic, character-based, overlapping, and page-bounded.

### 15.1 Boundary guarantee

Pages are cleaned and chunked separately. A chunk never spans two physical pages. This enables
genuine page-level citations later.

### 15.2 Window and breakpoint

The proposed end is the smaller of page length and **start + chunk_size**. If not at page end, the
chunker searches only the final 35% of the window for the latest:

1. Double-newline paragraph boundary.
2. Period followed by space.
3. Semicolon followed by space.
4. Space.

The furthest candidate wins. If none exists, the proposed hard end is used. This prevents tiny
chunks caused by early punctuation.

### 15.3 Overlap

After a non-final chunk, next start is **end - overlap**. Defensive logic forces forward progress.
Overlap never crosses a page.

### 15.4 Empty pieces and offsets

Stored text is stripped and empty pieces are skipped. No resulting chunks causes a
**ZERO_EXTRACTED_TEXT** error. **char_start/char_end** describe the chosen cleaned-page window;
stripping means boundary whitespace may not appear in stored text.

### 15.5 Ordering and identity

- **page_chunk_index** starts at zero on each page.
- **chunk_index** starts at zero per document and continues across pages.
- Chunks are stored in global-index order.

Fingerprint:

~~~text
document_id : page number : page chunk index : chunk text
~~~

SHA-256 is truncated to 24 hex characters and prefixed with **chk_**. Same ID, pages, cleaner, and
configuration yield the same chunk IDs. Fresh ingestion uses a new document ID and therefore new
chunk IDs.

## 16. Document metadata

~~~json
{
  "document_id": "doc_abc123...",
  "tenant_id": "default",
  "filename": "nist-zero-trust.pdf",
  "source": "manual",
  "source_file_id": null,
  "source_version": null,
  "document_version": 1,
  "checksum_sha256": "...",
  "content_type": "application/pdf",
  "file_size_bytes": 123456,
  "page_count": 59,
  "extracted_characters": 98765,
  "average_chars_per_page": 1673.98,
  "title": "Zero Trust Architecture",
  "author": null,
  "subject": null,
  "keywords": null,
  "status": "ACTIVE",
  "parser": "pymupdf",
  "parser_version": "...",
  "chunker_version": "paragraph-char-v2",
  "created_at": "...",
  "updated_at": "..."
}
~~~

Document IDs are **doc_** plus 20 hex characters from UUID4. Checksums, not IDs or filenames,
provide content identity. Source and document version are CLI-configurable. Source file/version
fields exist for future connectors but are not current CLI options.

## 17. Chunk metadata

~~~json
{
  "chunk_id": "chk_...",
  "tenant_id": "default",
  "document_id": "doc_...",
  "filename": "nist-zero-trust.pdf",
  "page": 23,
  "chunk_index": 54,
  "page_chunk_index": 2,
  "text": "...",
  "source": "manual",
  "document_version": 1,
  "checksum_sha256": "...",
  "chunker_version": "paragraph-char-v2",
  "char_start": 875,
  "char_end": 1370,
  "created_at": "..."
}
~~~

This retains tenant, page-local index, offsets, text, and checksum beyond the minimum contract.

## 18. Issue classifications

| Code | Severity | Trigger |
|---|---|---|
| **NOT_FOUND** | error | Missing path. |
| **NOT_A_FILE** | error | Path is not a regular file. |
| **NOT_PDF** | error | Missing **%PDF-** signature. |
| **CORRUPTED_PDF** | error | Read/parser open failure. |
| **PASSWORD_PROTECTED** | error | Password required. |
| **EMPTY_PDF** | error | Zero bytes or zero pages. |
| **ZERO_EXTRACTED_TEXT** | error | No useful text or chunks. |
| **LOW_TEXT_DENSITY** | warning | Average below configured threshold. |
| **DUPLICATE_DOCUMENT** | modeled | Dedicated exception is currently used. |
| **EXCESSIVE_PAGE_COUNT** | error | Page count exceeds policy. |
| **UNSUPPORTED_ENCODING** | error | Replacement ratio exceeds threshold. |
| **EXTRACTION_ERROR** | error | Page extraction exception. |

Issues contain code, severity, message, and structured details. Warnings do not block activation;
any error blocks the successful path.

## 19. Lifecycle

Successful Phase 1 path:

~~~text
RECEIVED → PARSING → CHUNKING → VALIDATING → ACTIVE
~~~

Preflight, extraction, quality, and empty-chunk failures move the record to **FAILED_PARSE**.
Status and issues are persisted during processing so created failed records remain inspectable.

## 20. SQLite and local files

~~~text
<data_dir>/
├── catalog.sqlite3
└── documents/
    └── doc_<id>/
        └── <sha256>.pdf
~~~

Phase 1 uses **documents**, **chunks**, and **validation_issues** tables. Connections enable foreign
keys and WAL. Methods commit on success, roll back on exception, and close connections. Chunk
replacement is transactional.

Indexes cover checksum, status, tenant, document/page chunk lookups, and issues. Older catalogs are
migrated forward with default tenant **default**.

After chunk validation, **shutil.copy2** stores the source PDF under its checksum. The stored path
is kept in SQLite and returned separately by inspect. Copy errors currently propagate without a
dedicated issue classification.

## 21. Developer CLI

### Validate

~~~bash
ragctl validate ./dataset/document.pdf
ragctl validate ./dataset/document.pdf --json
~~~

Returns validity, page count, checksum, metadata details, and issues. Errors exit 2. Validation does
not persist a document, though service initialization can create the catalog directory.

### Ingest

~~~bash
ragctl ingest ./dataset/document.pdf
ragctl ingest ./dataset/document.pdf \
  --source manual \
  --document-version 1 \
  --chunk-size 500 \
  --chunk-overlap 75 \
  --json
~~~

Success includes document, chunk count, stored path, and warnings. Rejection exits 2; duplicate
single ingestion exits 3 and prints the existing ID.

### Batch ingest

~~~bash
ragctl ingest-dir rag_pdf_corpus --limit 10
ragctl ingest-dir rag_pdf_corpus --limit 20
ragctl ingest-dir rag_pdf_corpus --limit 50
~~~

The table reports file, result, ID, and chunk count. Duplicates do not count as failures. Rejections
increment failures; processing continues, then exits 2 if any occurred.

### List and inspect

~~~bash
ragctl list
ragctl list --all
ragctl inspect doc_xxxxxxxxxxxxxxxxxxxx
ragctl inspect doc_xxxxxxxxxxxxxxxxxxxx --json
~~~

List is tenant-scoped and excludes deleted records unless **--all**. Inspect returns document,
issues, chunk count, and stored path. Missing/cross-tenant IDs exit 4.

### Chunks

~~~bash
ragctl chunks doc_xxxxxxxxxxxxxxxxxxxx
ragctl chunks doc_xxxxxxxxxxxxxxxxxxxx --page 23 --limit 100 --full
ragctl chunks doc_xxxxxxxxxxxxxxxxxxxx --json
~~~

Human output truncates text to 180 characters unless **--full**. Default limit is 20. Page filtering
uses physical one-based pages.

### Delete

~~~bash
ragctl delete doc_xxxxxxxxxxxxxxxxxxxx
ragctl delete doc_xxxxxxxxxxxxxxxxxxxx --keep-file
~~~

Deletion validates tenant, transitions through **DELETING**, removes chunks, purges the PDF by
default, tries to remove the empty directory, then marks **DELETED**. Metadata/issues remain as a
soft-deleted audit record. Repeated deletion is idempotent. If vectors exist, run **deindex** first.

### Exit codes

| Code | Meaning |
|---:|---|
| 0 | Success or warning-only validation. |
| 2 | Rejection or batch with failures. |
| 3 | Duplicate single ingestion. |
| 4 | Document absent from tenant scope. |

## 22. Smoke test

~~~bash
./scripts/phase1_smoke_test.sh \
  rag_pdf_corpus/ai-rag/01_attention_is_all_you_need.pdf
~~~

The script uses **.rag_data-smoke** unless **RAG_DATA_DIR** is set, deletes that directory,
validates, ingests, and lists. Do not set its data directory to a valuable or broad path because
the script intentionally resets it.

## 23. Test matrix

| Case | Verification |
|---|---|
| Valid text PDF | Active document, chunks, copy, metadata. |
| 1-page PDF | Basic extraction/chunk behavior. |
| 500-page PDF | Exact count and excessive-page classification at max 499. |
| Table PDF | Cell text remains searchable. |
| Image-only PDF | **ZERO_EXTRACTED_TEXT** and failed state. |
| Non-PDF | **NOT_PDF**. |
| Broken PDF | **CORRUPTED_PDF**. |
| Password-protected PDF | **PASSWORD_PROTECTED**. |
| Zero-page/zero-byte | **EMPTY_PDF**. |
| Duplicate | Existing ID returned. |
| Sparse text | Warning, not rejection. |
| Replacement characters | **UNSUPPORTED_ENCODING**. |
| Cleaner | Dehyphenation/paragraph normalization. |
| Chunker | Pages, order, overlap, deterministic IDs. |
| CLI integration | Ingest → inspect → chunks via JSON. |
| Delete | Chunks/file removed and status deleted. |

The 500-page test is marked **slow**:

~~~bash
make test       # excludes slow
make test-all   # includes slow
make check      # lint + fast suite
~~~

## 24. Determinism definition

Given identical PDF bytes, parser version, cleaner/chunker code, chunk configuration, extracted
pages, and document ID, the same texts, ordering, page assignments, offsets, and chunk IDs must
result.

Fresh ingestion generates a random document ID, so independent ingestions are not expected to have
identical chunk IDs. Parser upgrades can change text/order and should be treated as processing
version changes. Parser version is stored for this reason.

## 25. Gate evidence template

Record for each 10/20/50 run:

~~~text
Run date and Git revision:
Configuration and overrides:
PyMuPDF version:
Tenant and data directory:
Manifest/corpus revision:
Downloaded/attempted counts:
ACTIVE count:
Rejected count by issue:
Warning count by issue:
Total chunks:
Manual page/chunk samples:
Expected and unexpected failures:
Decision to advance:
~~~

The CLI does not currently generate this aggregate report automatically. Preserve command output
or query SQLite.

## 26. Troubleshooting

### Fewer than 50 downloads

Inspect **rag_pdf_corpus/failed**, retry transient URLs, and check for HTML responses. Never weaken
validation merely to admit a failed download.

### NOT_PDF

Inspect the first bytes and URL. Common causes are error/consent/rate-limit pages or mislabeled
files.

### CORRUPTED_PDF

Re-download and compare checksum/size. Preserve parser-specific failures as compatibility fixtures.

### PASSWORD_PROTECTED

Use an authorized unencrypted source. No password workflow exists.

### ZERO_EXTRACTED_TEXT

Determine whether the document is scanned/image-only. OCR is deliberately deferred.

### LOW_TEXT_DENSITY

Inspect samples. Diagram-heavy or short documents may be valid; this remains a warning.

### UNSUPPORTED_ENCODING

Inspect raw extraction and fonts. Raising the allowed replacement ratio can admit damaged text and
must be justified.

### EXCESSIVE_PAGE_COUNT

Confirm the count. Increase policy only with resource measurements and explicit review.

### Unexpected duplicate

Use a clean data directory when a fresh gate was intended. Same content in the tenant should be
rejected.

### Strange reading order/tables

Compare raw extraction to the page. Phase 1 is plain sorted text extraction, not a layout-aware
table/parser system.

### Changed chunks after dependency upgrade

Compare parser version, chunker version, settings, and extracted text. Rebuild under a new
processing version.

## 27. OCR boundary

OCR is intentionally deferred. Image-only PDFs fail instead of producing meaningless chunks.
A future OCR stage should record provider/model/version, page confidence, languages, preprocessing,
rotation, image resolution, and whether text is native or OCR-derived. OCR output must pass quality
checks before entering the cleaner/chunker.

## 28. Security and data handling

- PDF metadata/text are untrusted.
- Keep PyMuPDF patched; eventually isolate parsing of untrusted uploads.
- Filename is display metadata, never content identity.
- Tenant is stored on documents/chunks and enforced by developer operations.
- The data directory contains full text and PDFs and must be protected.
- The CLI is unauthenticated; filesystem access is the local trust boundary.
- Page count reduces one exhaustion risk but does not cap bytes, per-page complexity, parser time,
  or extracted-text size.

## 29. Current limitations

- No OCR or structured table extraction.
- No headings/layout blocks/bounding boxes.
- No header/footer or boilerplate removal.
- No maximum byte-size or per-page resource budget.
- No malware scan or sandboxed parser process.
- No automatic aggregate gate report.
- No concurrent/resumable batch ingestion.
- No connector population of source file/version fields.
- Copy errors lack a dedicated issue code.
- Duplicate attempts are not persisted as issue events.
- Physical page index is stored, not printed page labels.

These are explicit future improvements, not reasons to hide Phase 1 failures.

## 30. Acceptance checklist

### Corpus and gates

- [ ] Manifest has the intended 50 entries/categories.
- [ ] Download failures and non-PDF responses are reviewed.
- [ ] Immutable corpus checksums/revision are preserved.
- [ ] Gate 10 uses a clean directory and selected files are verified.
- [ ] Gate 20 uses a clean directory and broader layouts are inspected.
- [ ] Gate 50 attempts every file.
- [ ] Every rejection has an understood issue code.
- [ ] Active/rejected/warning/chunk totals are recorded.

### Processing and metadata

- [ ] SHA-256 duplicate detection works within tenant scope.
- [ ] Physical page numbers match source PDFs.
- [ ] Cleaner behavior is reviewed on dehyphenation/paragraphs.
- [ ] Chunks never cross pages.
- [ ] Global/page indices, offsets, text, checksum, and IDs persist.
- [ ] Parser/chunker versions persist.
- [ ] Canonical copies match recorded checksums.

### Bad-document tests

- [ ] Non-PDF and corrupt classifications pass.
- [ ] Password-protected classification passes.
- [ ] Empty and zero-page behavior passes.
- [ ] Image-only zero-text behavior passes.
- [ ] Low-density warning passes.
- [ ] Duplicate detection passes.
- [ ] Encoding rejection passes.
- [ ] 500-page excessive-count test passes with maximum 499.

### CLI and lifecycle

- [ ] Validate, ingest, batch, list, inspect, chunks, and delete are exercised.
- [ ] JSON output works for automation.
- [ ] Exit codes 2, 3, and 4 are verified.
- [ ] Failed records remain inspectable.
- [ ] Delete removes chunks and intentionally purges/retains the copy.

### Final decision

- [ ] Fast and complete test suites pass.
- [ ] Known limitations are accepted and recorded.
- [ ] All 50 produce deterministic success or explicit classification.
- [ ] Phase 2 begins only after Phase 1 evidence is complete.
