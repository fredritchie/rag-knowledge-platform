"""Exercise installed ML libraries without downloading or trusting remote model code."""

import math

import pytest

from rag_platform.config import EmbeddingSettings, RerankerSettings
from rag_platform.domain.models import SearchResult
from rag_platform.retrieval.embeddings import SentenceTransformerEmbedder
from rag_platform.retrieval.reranker import CrossEncoderReranker


def test_local_bert_embedding_and_reranking(tmp_path):
    pytest.importorskip("sentence_transformers")
    from sentence_transformers import SentenceTransformer, models
    from transformers import BertConfig, BertForSequenceClassification, BertModel, BertTokenizer

    # Random tiny models verify API compatibility, not retrieval quality.
    base = tmp_path / "base"
    base.mkdir()
    vocab = base / "vocab.txt"
    vocab.write_text("[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\nhello\nworld\n", encoding="utf-8")
    tokenizer = BertTokenizer(vocab_file=str(vocab))
    tokenizer.save_pretrained(base)
    config = BertConfig(
        vocab_size=len(tokenizer),
        hidden_size=16,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=32,
        num_labels=1,
    )
    BertModel(config).save_pretrained(base)
    transformer = models.Transformer(str(base), max_seq_length=32)
    sentence_model = SentenceTransformer(modules=[transformer, models.Pooling(16)], device="cpu")
    embedding_path = tmp_path / "embedding"
    sentence_model.save(str(embedding_path))
    embedder = SentenceTransformerEmbedder(
        EmbeddingSettings(
            model=str(embedding_path),
            dimension=16,
            device="cpu",
            query_prefix="",
        )
    )
    vectors = embedder.embed_documents(["hello world", "hello"])
    assert len(vectors) == 2
    assert all(len(vector) == 16 and all(math.isfinite(v) for v in vector) for vector in vectors)
    assert len(embedder.embed_query("hello")) == 16

    classifier_path = tmp_path / "classifier"
    BertForSequenceClassification(config).save_pretrained(classifier_path)
    tokenizer.save_pretrained(classifier_path)
    reranker = CrossEncoderReranker(RerankerSettings(model=str(classifier_path), device="cpu"))
    results = [
        SearchResult(
            chunk_id=f"chunk_{i}",
            tenant_id="test",
            document_id="doc",
            document_version=1,
            source="manual",
            page=1,
            filename="test.pdf",
            chunk_index=i,
            embedding_model_version="test",
            chunker_version="test",
            text=text,
            score=0,
        )
        for i, text in enumerate(["hello world", "world"])
    ]
    ranked = reranker.rerank("hello", results)
    assert len(ranked) == 2
    assert all(math.isfinite(result.reranker_score) for result in ranked)
    assert ranked[0].score >= ranked[1].score
