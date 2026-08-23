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
        return str(response.json()["response"]).strip()

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
                    token = json.loads(line).get("response", "")
                    if token:
                        yield token
