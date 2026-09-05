from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from rag_platform.domain.models import SearchResult
from rag_platform.security.rag import isolated_document_context


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    version: str
    system: str
    user: str


def load_prompt(prompt_dir: Path, version: str) -> PromptTemplate:
    path = prompt_dir / f"{version}.yaml"
    if not path.exists() and version.startswith("rag-"):
        path = prompt_dir / f"{version.removeprefix('rag-')}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt version not found: {path}")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PromptTemplate(
        version=value.get("version", version), system=value["system"], user=value["user"]
    )


def format_context(results: list[SearchResult], max_tokens: int) -> tuple[str, list[SearchResult]]:
    # Conservative dependency-free estimate. The LLM backend still enforces its native limit.
    max_chars = max_tokens * 4
    sections: list[str] = []
    included: list[SearchResult] = []
    used = 0
    for index, result in enumerate(results, 1):
        source_label = (
            f"[SOURCE {index}]\n"
            f"document_id: {result.document_id}\n"
            f"filename: {result.filename}\n"
            f"page: {result.page}\n"
            f"chunk_id: {result.chunk_id}"
        )
        section = (
            f"{source_label}\n"
            + isolated_document_context(text=result.text, source_label=f"SOURCE {index}")
            + "\n"
        )
        if used + len(section) > max_chars:
            remaining = max_chars - used
            if remaining > 200:
                sections.append(section[:remaining])
                included.append(result)
            break
        sections.append(section)
        included.append(result)
        used += len(section)
    return (
        "<AUTHORIZED_RETRIEVED_CONTEXT>\n"
        + "\n".join(sections)
        + "\n</AUTHORIZED_RETRIEVED_CONTEXT>",
        included,
    )
