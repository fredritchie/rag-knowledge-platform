from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Protocol

import httpx

from rag_platform.config import GenerationSettings


class LanguageModel(Protocol):
    model_version: str

    def generate(self, *, system: str, prompt: str) -> str: ...

    def stream(self, *, system: str, prompt: str) -> Iterator[str]: ...


class OllamaClient:
    def __init__(self, config: GenerationSettings):
        self.config = config
        self.model_version = config.model_version
        self.last_metrics: dict[str, float] = {}

    def _payload(self, system: str, prompt: str, stream: bool) -> dict[str, object]:
        return {
            "model": self.config.model,
            "system": system,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_output_tokens,
            },
        }

    def generate(self, *, system: str, prompt: str) -> str:
        response = httpx.post(
            f"{self.config.base_url.rstrip('/')}/api/generate",
            json=self._payload(system, prompt, False),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        self._record_metrics(body)
        return str(body["response"]).strip()

    def stream(self, *, system: str, prompt: str) -> Iterator[str]:
        with httpx.stream(
            "POST",
            f"{self.config.base_url.rstrip('/')}/api/generate",
            json=self._payload(system, prompt, True),
            timeout=self.config.timeout_seconds,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    body = json.loads(line)
                    self._record_metrics(body)
                    token = body.get("response", "")
                    if token:
                        yield token

    def _record_metrics(self, body: dict[str, object]) -> None:
        eval_count = body.get("eval_count")
        eval_duration = body.get("eval_duration")
        if isinstance(eval_count, int | float) and isinstance(eval_duration, int | float):
            seconds = float(eval_duration) / 1_000_000_000
            self.last_metrics = {
                "generated_tokens": float(eval_count),
                "tokens_per_second": float(eval_count) / seconds if seconds > 0 else 0.0,
            }
