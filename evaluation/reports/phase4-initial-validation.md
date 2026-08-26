# Phase 4 Initial Validation Results

## Scope

These results capture an initial functional validation of the Phase 4 retrieval and adversarial
RAG evaluation paths. They are curated from runs on an x86_64 AWS EC2 host with four logical CPUs,
approximately 15 GiB of memory, CPU-only Ollama inference, and chunk size 500.

Both datasets contained one case. Consequently, quality scores can only be zero or one, and the
reported mean, p50, and p95 retrieval latencies are the same single observation. The results are
not statistically meaningful production benchmarks and do not satisfy the Phase 4 exit criteria
on their own.

## Retrieval comparison

All strategies returned `21_nist_zero_trust.pdf` at rank one for the question "What is zero
trust?".

| Strategy | Hit@1 | Hit@3 | Hit@5 | MRR | Retrieval mean | Reranker mean |
|---|---:|---:|---:|---:|---:|---:|
| Dense | 1.0 | 1.0 | 1.0 | 1.0 | 153.42 ms | 0 ms |
| Hybrid | 1.0 | 1.0 | 1.0 | 1.0 | 1,297.84 ms | 0 ms |
| Hybrid plus reranker | 1.0 | 1.0 | 1.0 | 1.0 | 3,496.57 ms | 2,193.67 ms |

Dense retrieval is the provisional winner for this case because it produced the same rank with
substantially lower latency. This is not a final retrieval-mode selection: a representative
golden set must also cover semantic paraphrases, exact identifiers, multiple documents, and
page-level matches.

## Unsupported-question validation

The adversarial case asked for unsupported private information. After correcting generation to
remove sources from an insufficient-context response and aligning the evaluator's per-case
citation result with its aggregate definition, the run reported:

| Metric | Result |
|---|---:|
| Unsupported-question rejection | 1.0 |
| Citation correctness | 1.0 |
| Faithfulness proxy | 1.0 |
| Answer relevance proxy | 1.0 |
| Retrieval mean | 1,736.66 ms |
| Generation mean | 5,072.79 ms |
| End-to-end mean | 6,826.37 ms |

For rejected questions, faithfulness and answer relevance score one by evaluator definition. They
do not represent claim-level semantic quality for a generated answer.

## Known limitations and follow-up

- Expand the retrieval, normal RAG, and adversarial golden datasets beyond one case.
- Manually verify expected physical PDF page numbers.
- Rebuild and compare isolated chunk-size 300, 500, and 800 corpora.
- Compare Top-K 3, 5, and 10 using normal and adversarial RAG runs.
- Measure threshold, candidate-K, fusion, and reranker changes on the expanded dataset.
- Separate cold-start and warm latency reports.
- Align the Qdrant Python client and server versions before final benchmarking.
- Record hardware, corpus revision, model versions, and dataset revision for final runs.
