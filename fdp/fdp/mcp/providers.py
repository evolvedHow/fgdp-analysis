"""
LLM provider hooks for the NLQ translation step.

Design: a simple provider interface. To add a new AI model at deploy time
(e.g. an internal fine-tuned model), subclass ``BaseLLMProvider``, implement
``translate()``, and register it in ``PROVIDER_REGISTRY``. Then set
``AI_PROVIDER=<name>`` in the environment. No other code changes needed.

Local llama.cpp (Windows host, http://127.0.0.1:8080/v1) is supported out of
the box via its OpenAI-compatible chat completions endpoint.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any


class BaseLLMProvider(ABC):
    """Interface for all NLQ translation providers."""

    name: str

    @abstractmethod
    def translate(self, system_prompt: str, user_prompt: str) -> str:
        """
        Translate a natural-language redistricting question into a structured
        AnalysisParameters JSON string.

        Returns the raw JSON text from the model.
        """


# ---------------------------------------------------------------------------
# llama.cpp provider (local, OpenAI-compatible endpoint)
# ---------------------------------------------------------------------------

class LlamaCppProvider(BaseLLMProvider):
    """
    llama.cpp server (Windows native) at http://127.0.0.1:8080/v1.

    llama.cpp exposes an OpenAI-compatible chat completions endpoint, so we
    reuse the same request shape as OpenAI but point at the local host.

    Env vars:
        LLAMA_BASE_URL   default http://127.0.0.1:8080/v1
        LLAMA_MODEL      default: whatever model is loaded in llama.cpp
        LLAMA_API_KEY    optional; llama.cpp usually doesn't require one
    """

    name = "llama_cpp"

    def __init__(self) -> None:
        self.base_url = os.getenv("LLAMA_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
        self.model = os.getenv("LLAMA_MODEL", "llama.cpp")
        self.api_key = os.getenv("LLAMA_API_KEY", "")

    def translate(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"llama.cpp API error {e.code}: {e.read().decode()}")
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Cannot reach llama.cpp at {self.base_url}. "
                f"Is llama.cpp running on Windows host at http://127.0.0.1:8080/v1? "
                f"Underlying error: {e}"
            )


# ---------------------------------------------------------------------------
# Groq provider
# ---------------------------------------------------------------------------

class GroqProvider(BaseLLMProvider):
    name = "groq"

    def __init__(self) -> None:
        self.api_key = os.getenv("AI_API_KEY", "")
        self.model = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")

    def translate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("AI_API_KEY not set for groq provider")
        url = "https://api.groq.com/openai/v1/chat/completions"
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Groq API error {e.code}: {e.read().decode()}")


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------

class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self) -> None:
        self.api_key = os.getenv("AI_API_KEY", "")
        self.model = os.getenv("AI_MODEL", "gpt-4o-mini")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    def translate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("AI_API_KEY not set for openai provider")
        url = f"{self.base_url}/chat/completions"
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"OpenAI API error {e.code}: {e.read().decode()}")


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------

class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        self.api_key = os.getenv("AI_API_KEY", "")
        self.model = os.getenv("AI_MODEL", "claude-sonnet-4-6")

    def translate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("AI_API_KEY not set for anthropic provider")
        url = "https://api.anthropic.com/v1/messages"
        body = json.dumps({
            "model": self.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": 0.1,
            "max_tokens": 2000,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["content"][0]["text"]
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Anthropic API error {e.code}: {e.read().decode()}")


# ---------------------------------------------------------------------------
# Google provider
# ---------------------------------------------------------------------------

class GoogleProvider(BaseLLMProvider):
    name = "google"

    def __init__(self) -> None:
        self.api_key = os.getenv("AI_API_KEY", "")
        self.model = os.getenv("AI_MODEL", "gemini-flash-lite-latest")

    def translate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("AI_API_KEY not set for google provider")
        prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Google API error {e.code}: {e.read().decode()}")


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {
    "llama_cpp": LlamaCppProvider,
    "groq": GroqProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
}


def get_provider(name: str | None = None) -> BaseLLMProvider:
    """
    Instantiate an LLM provider by name.

    If name is None, reads AI_PROVIDER from the environment (default: llama_cpp).

    To add a new provider at deploy time:
        1. Subclass BaseLLMProvider and implement translate()
        2. Register it here: PROVIDER_REGISTRY["my_internal_model"] = MyInternalProvider
        3. Set AI_PROVIDER=my_internal_model in the environment
    """
    if name is None:
        name = os.getenv("AI_PROVIDER", "llama_cpp")

    name = name.lower()
    if name not in PROVIDER_REGISTRY:
        available = ", ".join(sorted(PROVIDER_REGISTRY))
        raise ValueError(
            f"Unknown AI provider '{name}'. Available: {available}"
        )

    return PROVIDER_REGISTRY[name]()


def list_providers() -> list[str]:
    """Return sorted list of registered provider names."""
    return sorted(PROVIDER_REGISTRY)
