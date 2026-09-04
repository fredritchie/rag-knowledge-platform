from __future__ import annotations

import uuid
from collections.abc import Iterator
from time import perf_counter

from rag_platform.config import Settings
from rag_platform.domain.models import Citation, RAGResponse
from rag_platform.generation.llm import LanguageModel, OllamaClient
from rag_platform.generation.prompts import format_context, load_prompt
from rag_platform.observability import (
    RAG_CITATIONS,
    RAG_GENERATED_TOKENS,
    RAG_GENERATION_TOKENS_PER_SECOND,
    RAG_QUERIES,
    RAG_STAGE_DURATION,
    observe_stage,
    service_var,
)
from rag_platform.retrieval.service import RetrievalService
from rag_platform.security.rag import secure_system_prompt, validate_model_output


class GenerationService:
    def __init__(
        self,
        settings: Settings,
        *,
        retrieval: RetrievalService | None = None,
        llm: LanguageModel | None = None,
    ):
        self.settings = settings
        self.retrieval = retrieval or RetrievalService(settings)
        self.llm = llm or OllamaClient(settings.generation)

    def answer(self, question: str, *, document_ids: set[str] | None = None) -> RAGResponse:
        started = perf_counter()
        results, retrieval_ms = self.retrieval.search(question, document_ids=document_ids)
        config = self.settings.generation
        parameters = {
            "temperature": config.temperature,
            "max_output_tokens": config.max_output_tokens,
            "max_context_tokens": config.max_context_tokens,
        }
        if not results:
            answer = config.insufficient_context_message
            included = []
            generation_ms = 0.0
        else:
            with observe_stage("prompt.build"):
                template = load_prompt(config.prompt_dir, config.prompt_version)
                context, included = format_context(results, config.max_context_tokens)
                prompt = template.user.format(
                    question=question,
                    context=context,
                    insufficient_context_message=config.insufficient_context_message,
                )
            generation_started = perf_counter()
            with observe_stage("llm.generate"):
                answer = validate_model_output(
                    self.llm.generate(
                        system=secure_system_prompt(
                            template.system, tools_enabled=self.settings.security.tools_enabled
                        ),
                        prompt=prompt,
                    ),
                    source_count=len(included),
                )
            generation_ms = (perf_counter() - generation_started) * 1000
            llm_metrics = getattr(self.llm, "last_metrics", {})
            generated_tokens = llm_metrics.get("generated_tokens")
            tokens_per_second = llm_metrics.get("tokens_per_second")
            if isinstance(generated_tokens, int | float):
                RAG_GENERATED_TOKENS.labels(service_var.get(), config.model_version).inc(
                    generated_tokens
                )
            if isinstance(tokens_per_second, int | float):
                RAG_GENERATION_TOKENS_PER_SECOND.labels(
                    service_var.get(), config.model_version
                ).set(tokens_per_second)

        elapsed_ms = (perf_counter() - started) * 1000
        outcome = "unsupported" if not results else "answered"
        RAG_QUERIES.labels(service_var.get(), outcome).inc()
        RAG_CITATIONS.labels(service_var.get()).observe(len(included))
        RAG_STAGE_DURATION.labels(service_var.get(), "end_to_end").observe(elapsed_ms / 1000)
        response = RAGResponse(
            answer=answer,
            sources=[
                Citation(
                    document_id=result.document_id,
                    filename=result.filename,
                    page=result.page,
                    chunk_id=result.chunk_id,
                    score=result.score,
                )
                for result in included
            ],
            model=config.model_version,
            prompt_version=config.prompt_version,
            latency_ms=elapsed_ms,
            retrieval_latency_ms=retrieval_ms,
            generation_latency_ms=generation_ms,
            retrieved_chunk_ids=[result.chunk_id for result in included],
            generation_parameters=parameters,
        )
        self.retrieval.catalog.record_generation(
            run_id="run_" + uuid.uuid4().hex,
            question=question,
            answer=answer,
            prompt_version=config.prompt_version,
            model_version=config.model_version,
            retrieved_chunk_ids=response.retrieved_chunk_ids,
            generation_parameters=parameters,
            latency_ms=elapsed_ms,
        )
        return response

    def stream_answer(
        self, question: str, *, document_ids: set[str] | None = None
    ) -> Iterator[str]:
        """Stream answer tokens while keeping retrieval and prompt construction centralized."""
        results, _ = self.retrieval.search(question, document_ids=document_ids)
        config = self.settings.generation
        if not results:
            yield config.insufficient_context_message
            return
        template = load_prompt(config.prompt_dir, config.prompt_version)
        context, included = format_context(results, config.max_context_tokens)
        prompt = template.user.format(
            question=question,
            context=context,
            insufficient_context_message=config.insufficient_context_message,
        )
        answer = "".join(
            self.llm.stream(
                system=secure_system_prompt(
                    template.system, tools_enabled=self.settings.security.tools_enabled
                ),
                prompt=prompt,
            )
        )
        yield validate_model_output(answer, source_count=len(included))
