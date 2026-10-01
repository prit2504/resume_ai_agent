from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def ok(label: str, detail: str = "") -> None:
    print(f"[OK]   {label}{': ' + detail if detail else ''}")


def fail(label: str, detail: str = "") -> None:
    print(f"[FAIL] {label}{': ' + detail if detail else ''}")


def check_http(name: str, url: str) -> bool:
    try:
        response = httpx.get(url, timeout=5)
        if response.status_code < 500:
            ok(name, f"{response.status_code} {url}")
            return True
        fail(name, f"{response.status_code} {url}")
    except Exception as exc:
        fail(name, str(exc))
    return False


def main() -> int:
    print("Resume AI Agent local setup check\n")

    provider = os.getenv("LLM_PROVIDER", "lmstudio").lower()
    if provider == "lmstudio":
        base = os.getenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
        check_http("LM Studio", f"{base}/models")
    elif provider == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
        check_http("Ollama OpenAI API", f"{base}/models")
    else:
        ok("LLM provider selected", provider)

    emb_provider = os.getenv("EMBEDDING_PROVIDER", "sentence_transformers").lower()
    if emb_provider == "sentence_transformers":
        try:
            from sentence_transformers import SentenceTransformer
            model_name = os.getenv(
                "LOCAL_EMBED_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2",
            )
            model = SentenceTransformer(model_name)
            dimension = model.get_sentence_embedding_dimension()
            ok("Local embeddings", f"{model_name} (dim={dimension})")
        except Exception as exc:
            fail("Local embeddings", str(exc))
    else:
        ok("Embedding provider selected", emb_provider)

    qdrant = os.getenv("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
    check_http("Qdrant", f"{qdrant}/collections")

    job_source = os.getenv("JOB_SOURCE", "fixture").lower()
    if job_source == "fixture":
        fixture = Path(os.getenv("LOCAL_JOBS_FIXTURE", "fixtures/jobs.json"))
        if not fixture.is_absolute():
            fixture = ROOT / fixture
        try:
            jobs = json.loads(fixture.read_text(encoding="utf-8"))
            ok("Local jobs fixture", f"{fixture} ({len(jobs)} jobs)")
        except Exception as exc:
            fail("Local jobs fixture", str(exc))
    else:
        if os.getenv("SERPAPI_API_KEY"):
            ok("SerpApi key", "configured")
        else:
            fail("SerpApi key", "JOB_SOURCE=serpapi but SERPAPI_API_KEY is empty")

    email_url = os.getenv("EMAIL_MCP_URL", "http://127.0.0.1:9000/mcp").rstrip("/")
    check_http("Email MCP", email_url)

    print("\nTip: fixture mode lets you test the full AI workflow without a SerpApi key.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
