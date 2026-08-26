from __future__ import annotations

import uuid
from collections.abc import Iterator
from time import perf_counter

from rag_platform.config import Settings
from rag_platform.domain.models import Citation, RAGResponse
from rag_platform.generation.llm import LanguageModel, OllamaClient
from rag_platform.generation.prompts import format_context, load_prompt
from rag_platform.retrieval.service import RetrievalService


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
            template = load_prompt(config.prompt_dir, config.prompt_version)
            context, included = format_context(results, config.max_context_tokens)
            prompt = template.user.format(
                question=question,
                context=context,
                insufficient_context_message=config.insufficient_context_message,
            )
            generation_started = perf_counter()
            answer = self.llm.generate(system=template.system, prompt=prompt)
            generation_ms = (perf_counter() - generation_started) * 1000
            
        answer = self.llm.generate(system=template.system, prompt=prompt)
        generation_ms = (perf_counter() - generation_started) * 1000

        if answer == config.insufficient_context_message:
            included = []    

        elapsed_ms = (perf_counter() - started) * 1000
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
        context, _ = format_context(results, config.max_context_tokens)
        prompt = template.user.format(
            question=question,
            context=context,
            insufficient_context_message=config.insufficient_context_message,
        )
        yield from self.llm.stream(system=template.system, prompt=prompt)
