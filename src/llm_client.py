#!/usr/bin/env python3
"""LLM client abstraction for Ollama and Foundry Local."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Optional

import httpx

try:
    from langchain_community.llms import Ollama
except Exception:  # pragma: no cover
    Ollama = None


@dataclass
class LLMConfig:
    provider: str
    model: str
    temperature: float = 0.3
    max_tokens: int = 2000


class LLMClient:
    async def invoke(self, prompt: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class OllamaClient(LLMClient):
    def __init__(self, config: LLMConfig):
        if Ollama is None:
            raise RuntimeError("Ollama client not available. Install langchain-community and ollama.")
        self._llm = Ollama(
            model=config.model,
            temperature=config.temperature,
            num_predict=config.max_tokens,
        )

    async def invoke(self, prompt: str) -> str:
        response = await asyncio.to_thread(self._llm.invoke, prompt)
        return response if isinstance(response, str) else response.content


class FoundryLocalClient(LLMClient):
    def __init__(self, config: LLMConfig):
        self.base_url = os.getenv("FOUNDRY_LOCAL_BASE_URL", "http://localhost:8000").rstrip("/")
        self.api_key = os.getenv("FOUNDRY_LOCAL_API_KEY")
        self.model = os.getenv("FOUNDRY_LOCAL_MODEL", config.model)
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens

    async def invoke(self, prompt: str) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": "You are a helpful code review assistant."},
                {"role": "user", "content": prompt},
            ],
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, content=json.dumps(payload))
            response.raise_for_status()
            data = response.json()

        return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def get_llm_client(model: str, temperature: float = 0.3, max_tokens: int = 2000) -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "foundry_local").lower()
    config = LLMConfig(provider=provider, model=model, temperature=temperature, max_tokens=max_tokens)

    if provider in {"foundry", "foundry_local", "foundry-local"}:
        return FoundryLocalClient(config)
    return OllamaClient(config)
