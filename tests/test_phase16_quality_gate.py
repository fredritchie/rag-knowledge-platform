from __future__ import annotations

from pathlib import Path

import pytest

from rag_platform.evaluation.quality_gate import evaluate_quality_gate
from rag_platform.release.gitops import update_image_manifest

BASELINE = {
    "minimum_cases": 3,
    "metrics": {
        "hit_at_5": {"report": "retrieval", "baseline": 0.9, "tolerance": 0.01},
        "groundedness": {"report": "rag", "baseline": 0.8, "tolerance": 0.02},
        "citation_correctness": {"report": "rag", "baseline": 0.95, "tolerance": 0.0},
    },
}


def test_quality_gate_passes_at_baseline_minus_tolerance() -> None:
    result = evaluate_quality_gate(
        {"cases": 3, "hit_at_5": 0.89},
        {"cases": 3, "groundedness": 0.78, "citation_correctness": 0.95},
        BASELINE,
    )
    assert result["passed"] is True
    assert result["failures"] == []


def test_quality_gate_fails_regressions_and_undersized_datasets() -> None:
    result = evaluate_quality_gate(
        {"cases": 2, "hit_at_5": 0.88},
        {"cases": 2, "groundedness": 0.77, "citation_correctness": 0.94},
        BASELINE,
    )
    assert result["passed"] is False
    assert len(result["failures"]) == 5


def test_gitops_manifest_accepts_only_complete_immutable_digest_set(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    digest = "sha256:" + "a" * 64
    for release_name in (
        "frontend",
        "api",
        "ingestion-worker",
        "drive-sync",
        "ollama-runtime",
    ):
        (artifacts / f"{release_name}.digest.txt").write_text(
            f"registry.example/rag/{release_name}@{digest}\n", encoding="utf-8"
        )
    manifest = tmp_path / "images.yaml"
    manifest.write_text("images: {}\n", encoding="utf-8")

    updated = update_image_manifest(artifacts, manifest)

    assert set(updated) == {"frontend", "api", "ingestionWorker", "driveSync", "ollamaRuntime"}
    assert digest in manifest.read_text(encoding="utf-8")

    (artifacts / "drive-sync.digest.txt").unlink()
    with pytest.raises(ValueError, match="Digest artifacts mismatch"):
        update_image_manifest(artifacts, manifest)

    (artifacts / "drive-sync.digest.txt").write_text(
        f"registry.example/rag/drive-sync@{digest}\n", encoding="utf-8"
    )
    (artifacts / "api.digest.txt").write_text("registry.example/rag/api:latest\n")
    with pytest.raises(ValueError, match="Invalid immutable image reference"):
        update_image_manifest(artifacts, manifest)
