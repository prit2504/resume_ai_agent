# Resume AI Agent - Project Information

## Purpose

Resume AI Agent searches Google Jobs listings, stores normalized jobs in Qdrant, matches them against a candidate resume, and generates role-specific resume advice.

## Stack

- Next.js + React frontend
- FastAPI backend
- SerpApi Google Jobs API for discovery
- Configurable LLM for extraction and advice
- Configurable embeddings
- Qdrant vector database
- PDF resume parsing
- Server-Sent Events for live progress

## Search Workflow

1. The frontend posts keywords and optional filters to `/api/v1/scrape/stream`.
2. `SerpApiGoogleJobsScraper` calls SerpApi with `engine=google_jobs`.
3. More pages use `serpapi_pagination.next_page_token`.
4. Search results are cached by SerpApi `job_id`.
5. Description, highlights, and application options are formatted for the existing LLM extractor.
6. Native SerpApi title/company/location values override LLM-extracted equivalents.
7. Jobs are embedded and upserted into Qdrant.
8. Progress is streamed to the frontend with SSE.

## Resume Matching

The resume is parsed into a structured profile, embedded, and searched against Qdrant. SerpApi application/source URLs are stored with each job and preserved in matched results.

## Resume Advice

The advisor compares the parsed resume to a selected matched job and returns targeted summary, skills, project, experience, and certification suggestions.

## Configuration

Required:

~~~dotenv
SERPAPI_API_KEY=your_serpapi_api_key_here
~~~

Optional:

~~~dotenv
SERPAPI_GOOGLE_DOMAIN=google.com
SERPAPI_GL=
SERPAPI_HL=en
SERPAPI_TIMEOUT_SECONDS=30
SERPAPI_NO_CACHE=false
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=google_jobs
~~~

## Filter Compatibility

To keep the current frontend/API contract:

- `date_posted` becomes a natural-language date query.
- `job_type`, `experience_level`, and `work_type` become query terms.
- `easy_apply` becomes a best-effort `"easy apply"` query.
- `sort_by=date` adds `recent` if no date filter is selected.
- `location=Remote` becomes a query term instead of a geographic origin.

## Run Locally

~~~bash
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
cd backend
pip install -r requirements.txt
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
~~~

Then:

~~~bash
cd frontend_v2
npm install
npm run dev
~~~

No LinkedIn login or MCP process is required.


## Human-in-the-loop Recruiter Outreach

The ingestion pipeline extracts literal emails and phone numbers from job source text. It may prefer recruiter/talent/HR-looking email addresses when several exist, but it never generates an address.

- `POST /api/v1/outreach/draft` creates an editable draft from the stored job and uploaded resume.
- `POST /api/v1/outreach/send` requires `approved=true`, validates the recipient belongs to that exact job, and calls the configured email MCP tool with the PDF resume attached.

## Resume-driven Discovery

`POST /api/v1/scrape/resume/stream` parses the resume, selects up to three target roles, searches Google Jobs for each role, combines results, deduplicates overlapping listings, ranks them, then runs the normal extraction/embedding/storage workflow.
