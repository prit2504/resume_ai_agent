from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI


@dataclass(frozen=True)
class ProviderConnection:
    name: str
    base_url: str
    api_key: str


def resolve_provider(provider: str, purpose: str) -> ProviderConnection:
    """Resolve an OpenAI-compatible provider from environment variables.

    purpose must be either "llm" or "embedding".
    """
    provider = (provider or "").strip().lower()
    if purpose not in {"llm", "embedding"}:
        raise ValueError("purpose must be 'llm' or 'embedding'")

    if provider == "lmstudio":
        return ProviderConnection(
            name="lmstudio",
            base_url=os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1"),
            api_key=os.environ.get("LMSTUDIO_API_KEY", "lm-studio"),
        )

    if provider == "ollama":
        return ProviderConnection(
            name="ollama",
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
            api_key=os.environ.get("OLLAMA_API_KEY", "ollama"),
        )

    if provider == "huggingface":
        return ProviderConnection(
            name="huggingface",
            base_url="https://router.huggingface.co/v1",
            api_key=os.environ.get("HF_TOKEN", ""),
        )

    if provider == "openai":
        return ProviderConnection(
            name="openai",
            base_url="https://api.openai.com/v1",
            api_key=os.environ.get("OPENAI_API_KEY", ""),
        )

    if provider == "gemini":
        return ProviderConnection(
            name="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.environ.get("GEMINI_API_KEY", ""),
        )

    if provider == "custom":
        prefix = "LLM" if purpose == "llm" else "EMBED"
        return ProviderConnection(
            name="custom",
            base_url=os.environ.get(f"{prefix}_BASE_URL", "").strip(),
            api_key=os.environ.get(f"{prefix}_API_KEY", "local"),
        )

    raise ValueError(
        f"Unsupported {purpose} provider '{provider}'. "
        "Use lmstudio, ollama, huggingface, openai, gemini, or custom."
    )


def build_client(provider: str, purpose: str) -> tuple[OpenAI, ProviderConnection]:
    connection = resolve_provider(provider, purpose)
    if not connection.base_url:
        raise RuntimeError(f"{purpose.upper()} base URL is empty for provider '{provider}'")
    client = OpenAI(base_url=connection.base_url, api_key=connection.api_key or "local")
    return client, connection


def provider_summary() -> dict[str, str | bool]:
    llm_name = os.environ.get("LLM_PROVIDER", "lmstudio").lower()
    emb_name = os.environ.get("EMBEDDING_PROVIDER", "lmstudio").lower()
    llm = resolve_provider(llm_name, "llm")
    emb = resolve_provider(emb_name, "embedding")
    return {
        "llm_provider": llm.name,
        "llm_base_url": llm.base_url,
        "embedding_provider": emb.name,
        "embedding_base_url": emb.base_url,
        "extractor_model": os.environ.get("EXTRACTOR_MODEL", ""),
        "advisor_model": os.environ.get("ADVISOR_MODEL", ""),
        "embedding_model": os.environ.get("EMBED_MODEL", ""),
        "job_source": os.environ.get("JOB_SOURCE", "serpapi").lower(),
        "serpapi_configured": bool(os.environ.get("SERPAPI_API_KEY")),
        "email_mcp_configured": bool(
            os.environ.get("EMAIL_MCP_URL") or os.environ.get("EMAIL_MCP_COMMAND")
        ),
    }
