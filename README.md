# Resume AI Agent — Google Jobs Matcher

## Overview

A modular AI career assistant that searches Google Jobs through SerpApi, streams live processing progress, normalizes listings with an LLM, embeds them into Qdrant, matches them against PDF resumes, and generates role-specific resume advice.

## Architecture

~~~text
Next.js frontend
      |
      | REST + SSE
      v
FastAPI / JobMatcherOrchestrator
      |
      +--> SerpApi Google Jobs --> descriptions + application links
      +--> LLMJobExtractor
      +--> UniversalEmbedder
      +--> Qdrant
      +--> PDFResumeParser
      +--> LLMResumeAdvisor
~~~

The SerpApi adapter preserves the existing scraper contract, so the extraction -> embedding -> storage -> matching -> advice workflow remains intact.

## Setup

1. Start Qdrant:

~~~bash
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
~~~

2. Configure the backend:

~~~bash
cd backend
cp .env.example .env
~~~

Set at minimum:

~~~dotenv
SERPAPI_API_KEY=your_serpapi_api_key_here
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=google_jobs
~~~

Also configure the LLM and embedding provider variables in `.env`.

3. Install and start the backend:

~~~bash
cd backend
python -m venv venv
pip install -r requirements.txt
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
~~~

4. Start the frontend:

~~~bash
cd frontend_v2
npm install
npm run dev
~~~

Open http://localhost:3000.

## Google Jobs Search

The backend sends `engine=google_jobs` to SerpApi. Pagination follows `serpapi_pagination.next_page_token`, with up to 10 results returned per page.

The existing UI filter schema is preserved. Date, job type, seniority, work type, Easy Apply, and date sorting are translated into best-effort query terms where Google Jobs has no stable direct filter equivalent.

Application links come from SerpApi `apply_options` when available, with the Google Jobs `share_link` as fallback.

## Environment Variables

| Variable | Purpose |
|---|---|
| `SERPAPI_API_KEY` | Required SerpApi key |
| `SERPAPI_GOOGLE_DOMAIN` | Google domain, default `google.com` |
| `SERPAPI_GL` | Optional country code |
| `SERPAPI_HL` | Language, default `en` |
| `SERPAPI_TIMEOUT_SECONDS` | HTTP timeout, default 30 |
| `SERPAPI_NO_CACHE` | Set `true` to bypass SerpApi cache |
| `QDRANT_COLLECTION` | Vector collection, default `google_jobs` |

## Notes

- LinkedIn cookies, MCP login, and the LinkedIn MCP server are no longer required.
- The legacy `linkedin_url` response field is retained as a frontend compatibility alias and resolves to the best available application/source URL.
- SerpApi usage is subject to your SerpApi account limits and plan.

## License

MIT License


## Recruiter Outreach with Human Approval

If a job description contains a literal email address or phone number, the backend stores that contact with the job. Contact extraction is deterministic from the source posting; the LLM does not invent recruiter details.

For a job with an email address:
1. Click **Draft HR Email**.
2. The LLM drafts a truthful email from the job + uploaded resume.
3. Review or edit recipient, subject, and body.
4. The PDF resume is attached.
5. Only **Approve & Send** calls the configured email MCP server.

The send endpoint rejects recipients that were not extracted from the same stored job.

### Email MCP configuration

~~~dotenv
EMAIL_MCP_TRANSPORT=streamable_http
EMAIL_MCP_URL=http://127.0.0.1:9000/mcp
EMAIL_MCP_TOOL_NAME=send_email
~~~

For stdio:

~~~dotenv
EMAIL_MCP_TRANSPORT=stdio
EMAIL_MCP_COMMAND=python
EMAIL_MCP_ARGS_JSON=["path/to/email_mcp_server.py"]
EMAIL_MCP_TOOL_NAME=send_email
~~~

The bundled Email MCP tool is `send_email(to_email, subject, body, pdf_base64, pdf_filename)`. The Resume AI Agent sends the approved resume PDF as base64, so the backend and MCP server do not need a shared local file path.

## Search Improvements in this Branch

- SerpApi-native country (`gl`), language (`hl`), radius (`lrad`) and optional `uds` support.
- Duplicate-job detection and lightweight relevance/recency ranking before LLM extraction and Qdrant storage.
- Resume-driven multi-role discovery that searches up to three parsed target roles and merges/deduplicates results.


## Zero-Cost Local Development

You can run the AI parts of this project without OpenAI, Gemini, or other paid model APIs.

Recommended local stack:

~~~text
LM Studio                  -> chat / structured generation
sentence-transformers      -> embeddings
Qdrant                     -> vector search
local fixture jobs         -> job source while testing
Email MCP                  -> SMTP sending after human approval
FastAPI + Next.js          -> application
~~~

LM Studio exposes an OpenAI-compatible API, so the existing OpenAI Python client can talk to a model running locally. The default project configuration uses:

~~~dotenv
LLM_PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1

EMBEDDING_PROVIDER=sentence_transformers
LOCAL_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2

JOB_SOURCE=fixture
LOCAL_JOBS_FIXTURE=fixtures/jobs.json
~~~

### 1. Configure LM Studio

Download/load an instruction-tuned model in LM Studio and start its local server.

Use the exact model identifier shown by LM Studio for all three generation tasks:

~~~dotenv
LLM_MODEL=your-loaded-model-id
EXTRACTOR_MODEL=your-loaded-model-id
ADVISOR_MODEL=your-loaded-model-id
~~~

The same chat model is used for:
- resume structuring,
- job-field extraction,
- resume advice,
- recruiter outreach drafting.

A smaller instruction model can work for testing, but reliable JSON output is important.

### 2. Copy the ready LM Studio preset

From the backend directory:

~~~bash
copy configs\lmstudio.env.example .env
~~~

On macOS/Linux:

~~~bash
cp configs/lmstudio.env.example .env
~~~

Then replace `your-loaded-lm-studio-model` with the actual LM Studio model identifier.

Other presets are available:

~~~text
backend/configs/lmstudio.env.example
backend/configs/ollama.env.example
backend/configs/huggingface.env.example
backend/configs/custom-openai-compatible.env.example
~~~

### 3. Start Qdrant

~~~bash
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
~~~

The default local embedding model is `all-MiniLM-L6-v2`. If you change embedding models, use a new Qdrant collection name because vector dimensions may differ.

### 4. Start the Email MCP server

~~~bash
cd email_mcp_server
pip install -r requirements.txt
copy .env.example .env
python server.py
~~~

Configure your SMTP/Gmail app password in `email_mcp_server/.env`.

The MCP endpoint defaults to:

~~~text
http://127.0.0.1:9000/mcp
~~~

### 5. Start the backend

~~~bash
cd backend
pip install -r requirements.txt
python scripts/check_local_setup.py
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
~~~

You can inspect the non-secret active configuration at:

~~~text
GET http://127.0.0.1:8000/api/v1/config
~~~

### 6. Start the frontend

~~~bash
cd frontend_v2
npm install
npm run dev
~~~

Open:

~~~text
http://localhost:3000
~~~

### Testing without a job API key

Keep:

~~~dotenv
JOB_SOURCE=fixture
~~~

The application reads `backend/fixtures/jobs.json`, so you can test:

~~~text
resume upload
 -> resume parsing with LM Studio
 -> multi-role discovery
 -> job extraction
 -> local embeddings
 -> Qdrant matching
 -> recruiter-contact extraction
 -> email drafting
 -> human approval UI
 -> Email MCP integration
~~~

The included fixture uses placeholder email domains. To test a real SMTP send, replace one fixture contact with an email address you control, re-run the fixture ingestion, and send only to that test address.

### Switching to live Google Jobs

When you want live jobs:

~~~dotenv
JOB_SOURCE=serpapi
SERPAPI_API_KEY=your_key
~~~

No other code change is needed.

### Hugging Face options

For a Hugging Face model with no paid inference API, the simplest path is to download/run that model through LM Studio and keep `LLM_PROVIDER=lmstudio`.

If you use Hugging Face hosted inference instead, switch to:

~~~dotenv
LLM_PROVIDER=huggingface
HF_TOKEN=your_huggingface_token
EXTRACTOR_MODEL=your-supported-chat-model
ADVISOR_MODEL=your-supported-chat-model
~~~

For another local OpenAI-compatible server such as vLLM or TGI, use `LLM_PROVIDER=custom` and set `LLM_BASE_URL`.
