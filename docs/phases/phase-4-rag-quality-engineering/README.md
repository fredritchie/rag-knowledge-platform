# Phase 4 — RAG Quality Engineering

## 1. Purpose

Phase 4 makes retrieval and generation choices measurable. It adds BM25 lexical search, dense and
lexical fusion, optional cross-encoder reranking, version-controlled golden datasets, quality
metrics, stage latency metrics, and repeatable experiment guidance.

The target corpus contains exact identifiers—RFC numbers, NIST control IDs, CVEs, IP addresses,
service names, policy names, and acronyms—that dense retrieval may understand imperfectly. BM25
preserves exact-token evidence while dense search handles paraphrases. Reranking then evaluates
query/passage pairs more precisely over a bounded candidate set.

## 2. Exit criterion

Phase 4 is accepted when measured reports explain the selected production configuration:

- Dense-only, hybrid, and hybrid-plus-reranker runs use the same golden dataset.
- Chunk sizes 300, 500, and 800 are compared using cleanly rebuilt corpora/indexes.
- Top-K values 3, 5, and 10 are compared for downstream answer quality and latency.
- Hit@1, Hit@3, Hit@5, MRR, and retrieval latency are recorded.
- Reranker, generation, and end-to-end latency are recorded where applicable.
- Citation correctness, unsupported-question rejection, and groundedness/faithfulness proxies are
  recorded and manually audited.
- The winning configuration is chosen from evidence rather than defaults or intuition.

## 3. Retrieval architecture

```text
                         Query
                           │
              ┌────────────┴────────────┐
              │                         │
        BGE dense search          Local BM25 search
              │                         │
              └────────────┬────────────┘
                           │
                    RRF or weighted fusion
                           │
                    candidate_k results
                           │
                  optional cross-encoder
                           │
                       final top_k
                           │
                           LLM
```

Modes:

| Mode | Dense | BM25 | Fusion | Reranker |
|---|---:|---:|---:|---:|
| `dense` | yes | no | no | no |
| `hybrid` | yes | yes | yes | no |
| `hybrid_rerank` | yes | yes | yes | yes when configured |

Passing `--mode` to `ragctl search` overrides only the mode for that call. Other retrieval and
reranker settings still come from configuration.

## 4. Relevant source files

| Responsibility | File |
|---|---|
| BM25 tokenization and scoring | `src/rag_platform/retrieval/lexical.py` |
| Fusion and stage timing | `src/rag_platform/retrieval/service.py` |
| Cross-encoder provider | `src/rag_platform/retrieval/reranker.py` |
| Evaluation runner and metrics | `src/rag_platform/evaluation/service.py` |
| Evaluation item model | `src/rag_platform/domain/models.py` |
| Retrieval golden set | `evaluation/datasets/retrieval-golden.jsonl` |
| RAG golden set | `evaluation/datasets/rag-golden.jsonl` |
| Unsupported/adversarial set | `evaluation/datasets/adversarial.jsonl` |
| Generated reports | `evaluation/reports/` |

## 5. Configuration

```yaml
retrieval:
  mode: hybrid_rerank
  top_k: 5
  candidate_k: 20
  similarity_threshold: 0.65
  dense_weight: 0.65
  lexical_weight: 0.35
  fusion: rrf
  rrf_k: 60

reranker:
  enabled: true
  provider: sentence_transformers
  model: cross-encoder/ms-marco-MiniLM-L-6-v2
  model_version: ms-marco-MiniLM-L-6-v2
  batch_size: 16
  device: cpu

evaluation:
  retrieval_dataset: evaluation/datasets/retrieval-golden.jsonl
  rag_dataset: evaluation/datasets/rag-golden.jsonl
  adversarial_dataset: evaluation/datasets/adversarial.jsonl
  report_dir: evaluation/reports
  latency_percentiles: [50, 95]
```

### Retrieval fields

| Field | Detailed behavior |
|---|---|
| `mode` | Selects dense, hybrid, or hybrid-rerank control flow. |
| `top_k` | Final number of results returned to generation/caller. |
| `candidate_k` | Maximum dense and lexical candidates gathered before fusion/reranking. The effective value is at least `top_k`. |
| `similarity_threshold` | Dense Qdrant cutoff applied before fusion. BM25 can still add chunks absent from dense results. |
| `dense_weight` | Dense contribution during RRF or weighted fusion. |
| `lexical_weight` | BM25 contribution during RRF or weighted fusion. |
| `fusion` | Either `rrf` or `weighted`. |
| `rrf_k` | Rank constant controlling how quickly reciprocal-rank contribution decays. |

Weights are non-negative but are not required to sum to one. Their ratio determines relative
influence. Configuring both to zero produces meaningless equal fusion scores and should be avoided.

### Reranker fields

`enabled: false` or `provider: none` selects a no-op reranker. The configured cross-encoder scores
every `(query, candidate text)` pair in batches, replaces the displayed final score with its own
float score, stores that score in `reranker_score`, and sorts descending.

Cross-encoder scores are model-specific and are not guaranteed to be probabilities or bounded to
zero through one. Do not reuse the dense similarity threshold as a reranker threshold.

## 6. BM25 implementation details

Lexical tokenization lowercases text and extracts this pattern:

```text
[a-z0-9_.:/-]+
```

The punctuation retained inside tokens is intentional for exact technical identifiers such as:

- `nist-sp-800-53`
- `rfc-9110`
- `cve-2025-1234`
- `10.0.0.1`
- `service/name`

BM25 is computed over every active SQLite chunk belonging to the configured tenant for each
query. The implementation uses:

- `k1 = 1.5`
- `b = 0.75`
- corpus-local document frequency
- average chunk token length

Only chunks with a positive lexical score are returned. There is currently no persistent inverted
index, stemming, stop-word filtering, synonym expansion, field weighting, or language-specific
analyzer. This is correct for a development corpus but has O(number of chunks) query-time work and
will need a dedicated lexical engine at production scale.

## 7. Fusion algorithms

### 7.1 Reciprocal Rank Fusion

For every dense result at one-based rank `r`:

```text
dense contribution = dense_weight / (rrf_k + r)
```

For every lexical result at one-based rank `r`:

```text
lexical contribution = lexical_weight / (rrf_k + r)
```

Contributions for the same chunk ID are added, then all chunks are sorted by total descending.
RRF uses ordering instead of raw score scale, which is useful because cosine similarity and BM25
scores are not naturally comparable.

### 7.2 Weighted normalized fusion

Dense scores are divided by the maximum dense score in that result set. BM25 scores are divided
by the maximum lexical score. Contributions are then:

```text
score = dense_weight × normalized_dense + lexical_weight × normalized_lexical
```

Chunks present in only one list receive only that component. Max values fall back to one to avoid
division by zero.

Weighted fusion preserves within-query score magnitude but is more sensitive to outliers and
score-distribution changes than RRF. Measure both on exact-term and paraphrase subsets.

## 8. Candidate generation and reranking

Both dense and BM25 branches request up to `candidate_k`. Their union can exceed `candidate_k`
after fusion because each branch may return different chunks. The current implementation passes
the entire fused union to the reranker and truncates only after reranking.

This means worst-case reranker work can approach `2 × candidate_k` query/passage pairs. Account
for that when sizing `batch_size` and interpreting latency. A future optimization may truncate the
fused list before reranking, but that would change measured recall and must be treated as a new
experiment.

## 9. Golden dataset contracts

### 9.1 Retrieval dataset

One JSON object per line:

```json
{
  "question": "Which RFC defines HTTP semantics?",
  "expected_document": "32_rfc9110_http_semantics.pdf",
  "expected_pages": [1, 2],
  "expected_answer": null,
  "should_answer": true
}
```

### 9.2 RAG dataset

```json
{
  "question": "What does zero trust assume about network location?",
  "expected_document": "NIST-SP-800-207.pdf",
  "expected_pages": [4],
  "expected_answer": "No implicit trust is granted based only on network location.",
  "should_answer": true
}
```

### 9.3 Adversarial/unsupported dataset

```json
{
  "question": "What is the CEO's private phone number?",
  "expected_document": "none",
  "expected_pages": [],
  "expected_answer": null,
  "should_answer": false
}
```

The evaluator currently selects `retrieval_dataset` for retrieval runs and `rag_dataset` for RAG
runs. `adversarial_dataset` is configured and version-controlled but is not automatically merged
into a RAG run. Run it explicitly with `--dataset` or create a combined RAG JSONL file.

Comments are allowed only as full lines beginning with `#`. Blank lines are ignored. Other lines
must validate against `RetrievalEvaluationItem`.

## 10. Retrieval metric definitions

For each question, a result matches when:

1. `expected_document` equals the result's document ID, filename, or filename stem; and
2. `expected_pages` is empty, or the result page is in `expected_pages`.

The first matching one-based rank is used.

### Hit@K

```text
Hit@K = questions with first matching rank ≤ K / total questions
```

The implementation reports Hit@1, Hit@3, and Hit@5.

### Mean Reciprocal Rank

```text
reciprocal rank = 1 / first matching rank
no match = 0
MRR = mean reciprocal rank across questions
```

### Latency

The report contains mean retrieval latency plus configured nearest-rank percentiles. With default
`[50, 95]`, it emits `retrieval_latency_ms_p50` and `retrieval_latency_ms_p95`.

The percentile implementation sorts observations and selects:

```text
round((percentile / 100) × (count - 1))
```

This is appropriate for development summaries but differs from interpolated percentile methods
used by some monitoring systems.

The retrieval report also includes mean reranker latency from `RetrievalService.last_metrics`.

## 11. RAG metric definitions and limitations

### Citation correctness

For answerable questions, the score is one if any structured source matches the expected document
and expected page rules. For unsupported questions, it is one only when the response has no
sources.

This measures source selection, not whether each natural-language claim is entailed by its inline
citation.

### Unsupported-question rejection

Only rows with `should_answer: false` contribute. A row passes when the answer exactly equals the
configured `insufficient_context_message`. Punctuation or wording variations count as failures.

### Answer relevance

The evaluator lowercases and tokenizes the expected and generated answers, removes a small fixed
English stop-word set, and reports the fraction of expected content tokens appearing in the
generated answer. This is a lexical proxy, not semantic correctness.

### Faithfulness and groundedness proxy

Retrieved chunk text is loaded from SQLite. The evaluator reports the fraction of generated
answer content tokens that also appear in the retrieved context. Rejected questions score one.
The current report uses this same value for both `faithfulness` and `groundedness`.

This proxy can reward copied but incorrect text and penalize valid paraphrases. It is not a
claim-level entailment evaluator. Production selection should combine it with manual review or a
separately validated judge model.

### Latency

RAG reports include mean:

- retrieval latency
- generation latency
- end-to-end latency

The total includes retrieval, prompt construction, Ollama generation, response construction, and
minor local overhead. SQLite persistence occurs after the total is captured.

## 12. Running evaluations

Retrieval:

```bash
ragctl evaluate retrieval
ragctl evaluate retrieval \
  --dataset evaluation/datasets/retrieval-golden.jsonl \
  --report-name hybrid-rerank-c500-k5
```

RAG:

```bash
ragctl evaluate rag
ragctl evaluate rag \
  --dataset evaluation/datasets/adversarial.jsonl \
  --report-name adversarial-hybrid-rerank
```

The CLI prints the report and writes `<report_dir>/<report-name>.json`. Choose unique names; an
existing report with the same name is overwritten.

## 13. Required experiment matrix

At minimum compare:

```text
retrieval mode:
  dense
  hybrid
  hybrid_rerank

chunk size:
  300
  500
  800

top_k:
  3
  5
  10
```

This is 27 combinations before fusion and prompt variants. Use staged experiments rather than
changing every variable simultaneously:

1. Fix chunk size 500 and top-K 5; select retrieval mode/fusion.
2. Fix the winning retrieval mode; select chunk size.
3. Fix retrieval and chunking; select top-K using RAG quality and latency.
4. Tune threshold, candidate count, fusion weights, and reranker model around the winner.
5. Compare prompt versions only after retrieval is fixed.

## 14. Rebuilding chunk-size experiments correctly

Chunk size changes require re-ingestion because SQLite stores the actual chunk text and offsets.
They should also use distinct Qdrant collections to avoid mixing old and new chunk IDs.

Example for size 300:

```bash
export RAG_DATA_DIR=.rag_data_c300
export RAG__CHUNKING__SIZE=300
export RAG__CHUNKING__OVERLAP=45
export RAG__CHUNKING__VERSION=paragraph-char-c300-v1
export RAG__QDRANT__COLLECTION=rag_chunks_c300

ragctl ingest-dir rag_pdf_corpus
ragctl index --all
ragctl evaluate retrieval --report-name dense-c300-k5
```

Repeat with isolated data directories and collection names for 500 and 800. Keep overlap policy
explicit; using a constant 75-character overlap and using a constant 15% overlap are different
experiments.

Do not compare a new YAML chunk size against an old catalog and call it a chunk-size experiment.
Configuration changes do not mutate existing chunk records.

## 15. Retrieval-mode experiment commands

Dense baseline:

```bash
RAG__RETRIEVAL__MODE=dense \
ragctl evaluate retrieval --report-name dense-c500-k5
```

Hybrid RRF:

```bash
RAG__RETRIEVAL__MODE=hybrid \
RAG__RETRIEVAL__FUSION=rrf \
ragctl evaluate retrieval --report-name hybrid-rrf-c500-k5
```

Hybrid plus reranker:

```bash
RAG__RETRIEVAL__MODE=hybrid_rerank \
RAG__RERANKER__ENABLED=true \
ragctl evaluate retrieval --report-name hybrid-rerank-c500-k5
```

Weighted fusion:

```bash
RAG__RETRIEVAL__MODE=hybrid \
RAG__RETRIEVAL__FUSION=weighted \
RAG__RETRIEVAL__DENSE_WEIGHT=0.65 \
RAG__RETRIEVAL__LEXICAL_WEIGHT=0.35 \
ragctl evaluate retrieval --report-name hybrid-weighted-65-35
```

## 16. Top-K experiments

`retrieval.top_k` affects how many chunks are passed to generation. Retrieval evaluation itself
always asks for five results to calculate fixed Hit@1/3/5, so changing configured top-K does not
change those retrieval metrics in the current evaluator.

Top-K must therefore be evaluated with RAG runs or direct search inspection:

```bash
RAG__RETRIEVAL__TOP_K=3 ragctl evaluate rag --report-name rag-k3
RAG__RETRIEVAL__TOP_K=5 ragctl evaluate rag --report-name rag-k5
RAG__RETRIEVAL__TOP_K=10 ragctl evaluate rag --report-name rag-k10
```

Increasing top-K can improve evidence coverage while also increasing context noise, prompt size,
generation latency, and the chance of distracting the LLM.

## 17. Dataset design guidance

A useful golden set should be stratified, not merely large. Tagging is not represented in the
current schema, so maintain separate JSONL files or external analysis metadata for categories:

- semantic paraphrases
- exact RFC/NIST/CVE identifiers
- acronyms and product/service names
- answers contained on one page
- answers requiring adjacent pages
- tables and lists
- similar documents with one correct version
- unsupported questions
- misleading premise questions
- prompt-injection-like document content
- very short and very long questions

Avoid using only questions copied verbatim from source text; that overestimates lexical retrieval
quality. Avoid expected pages based on a PDF viewer's printed page label when the ingested page
number is the physical one-based PDF page index.

## 18. Reading experiment results

Prefer configurations that improve the target metric without unacceptable regression elsewhere.
Examples:

- Higher Hit@5 with unchanged Hit@1 may help generation but does not improve the first result.
- Higher MRR with much higher reranker latency may be a poor interactive tradeoff.
- Dense-only may win semantic questions while hybrid wins identifier questions; category-level
  results can justify hybrid even if aggregate differences are small.
- A larger chunk may improve answer completeness but lower page-level precision and consume more
  context.
- A higher threshold may improve rejection while removing correct low-score paraphrases.

Record configuration, corpus checksum/version, model versions, prompt version, dataset revision,
hardware, warm/cold state, and report filename for every decision-worthy run.

## 19. Reproducibility controls

- Use a distinct Qdrant collection for each embedding dimension/model or chunk rebuild.
- Record `embedding.model_version`, `reranker.model_version`, and `generation.model_version`.
- Keep prompt YAML and golden JSONL changes in version control.
- Use temperature zero for baseline generation comparisons.
- Warm models before latency measurement or explicitly label cold-start results.
- Do not mix reports from different CPU/GPU devices without noting hardware.
- Keep tenant and corpus constant across configuration comparisons.
- Preserve raw per-question results, not only averages.

## 20. Current quality-engineering limitations

- BM25 scans all tenant chunks per query and is not production-scale.
- Retrieval reports do not include per-stage dense/BM25/fusion timings, although the service
  records them in memory; only total and reranker mean are emitted.
- The evaluator has no bootstrap confidence intervals or significance tests.
- The evaluator does not automatically run a configuration matrix.
- RAG groundedness/faithfulness are lexical overlap proxies.
- Inline citation markers are not parsed or claim-aligned.
- Adversarial rows are not automatically merged with normal RAG rows.
- Generation reports do not include p50/p95 latencies.
- Evaluation report writes overwrite an existing same-name file.
- No judge-model calibration or human-review workflow is implemented.

These limitations must be stated with results so proxy scores are not presented as stronger
evidence than they are.

## 21. Failure modes and troubleshooting

### BM25 dominates exact terms but hurts paraphrases

Reduce lexical weight, use RRF, increase dense weight, or add category-balanced questions before
tuning. Do not optimize from one RFC lookup.

### Dense candidates disappear in hybrid mode

The dense similarity threshold is applied before fusion. Lower it or set it to `null` during
candidate-generation experiments.

### Reranker latency is excessive

Reduce `candidate_k`, increase batch size if memory permits, use an accelerator, select a smaller
cross-encoder, or disable reranking. Remember that the fused union can approach twice the branch
candidate count.

### Reranker scores look unlike similarity scores

That is expected. Cross-encoder output is model-specific; compare ordering and measured metrics,
not the absolute value against the Qdrant cosine threshold.

### Retrieval report has zero hits

Check filename/stem/document-ID spelling, expected physical page numbers, tenant, indexed
collection, threshold, and dataset/corpus alignment.

### Unsupported rejection is zero

Ensure the selected dataset actually contains `should_answer: false` rows, the insufficient
message matches exactly, and irrelevant retrieval results are not bypassing the Python fallback.

## 22. Testing

Run static and offline tests:

```bash
make check
```

The phase tests validate metric arithmetic on a known hit, configuration overrides, payload
metadata, retrieval ordering, and generation persistence using deterministic substitutes. Live
quality evaluation remains mandatory because test doubles cannot measure BGE, cross-encoder, or
LLM behavior.

## 23. Production configuration decision record template

For the final selected configuration, record:

```text
Corpus/version:
Evaluation dataset revision:
Hardware:
Embedding model/version:
Chunk size/overlap/version:
Qdrant collection:
Dense threshold:
Retrieval mode:
Candidate K / final K:
Fusion algorithm / weights / RRF K:
Reranker model/version/batch/device:
Generation model/version:
Prompt version:

Hit@1:
Hit@3:
Hit@5:
MRR:
Retrieval mean/p50/p95:
Reranker mean:
Citation correctness:
Unsupported rejection:
Faithfulness proxy:
Answer relevance proxy:
Generation mean:
End-to-end mean:

Rejected alternatives and why:
Known limitations:
Approver/date:
```

## 24. Acceptance checklist

- [ ] Golden datasets contain representative semantic, exact-term, and unsupported questions.
- [ ] Expected physical PDF pages were manually verified.
- [ ] Dense, hybrid, and hybrid-rerank reports use the same corpus and retrieval dataset.
- [ ] RRF and weighted fusion were compared or a reason for excluding one is recorded.
- [ ] Chunk 300/500/800 corpora were actually rebuilt into isolated data/index locations.
- [ ] Top-K 3/5/10 were compared using RAG metrics, not only fixed retrieval Hit@K.
- [ ] Threshold and candidate-K changes were measured.
- [ ] Reranker quality gain is weighed against its measured latency.
- [ ] Normal and adversarial RAG datasets were both run.
- [ ] Proxy limitations are included alongside RAG scores.
- [ ] Several answers and citations were manually audited against original PDFs.
- [ ] The final configuration decision record is complete and reproducible.
