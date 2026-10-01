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
EMAIL_MCP_URL=http://localhost:8081/mcp
EMAIL_MCP_TOOL_NAME=send_email
~~~

For stdio:

~~~dotenv
EMAIL_MCP_TRANSPORT=stdio
EMAIL_MCP_COMMAND=python
EMAIL_MCP_ARGS_JSON=["path/to/email_mcp_server.py"]
EMAIL_MCP_TOOL_NAME=send_email
~~~

The adapter currently expects the send tool to accept `to`, `subject`, `body`, and an `attachments` array with `filename`, `content_type`, and `content_base64`.

## Search Improvements in this Branch

- SerpApi-native country (`gl`), language (`hl`), radius (`lrad`) and optional `uds` support.
- Duplicate-job detection and lightweight relevance/recency ranking before LLM extraction and Qdrant storage.
- Resume-driven multi-role discovery that searches up to three parsed target roles and merges/deduplicates results.
