# LinkedIn Job Matcher - Complete Project Information

This document serves as the comprehensive source of truth for the LinkedIn Job Matcher project, covering the architecture, workflows, setup, and configurations.

## 1. Project Overview

LinkedIn Job Matcher is a modular, AI-powered system that automates the process of finding relevant jobs on LinkedIn, matching them against your specific resume, and generating tailored advice to improve your chances of landing an interview.

It achieves this by combining:
- **Model Context Protocol (MCP)** for reliable LinkedIn data extraction natively via `stdio`.
- **Large Language Models** for structured field extraction and resume advice (supports OpenAI, Gemini, HuggingFace, or local Ollama).
- **Server-Sent Events (SSE)** for real-time live progress streaming to the UI.
- **Local Vector Database (Qdrant)** for semantic similarity search.
- **FastAPI** for backend orchestration with asynchronous concurrency.
- **Next.js (App Router)** for a modern, responsive frontend dashboard.

## 2. Architecture & Tech Stack

### Frontend (`/frontend_v2`)
- **Framework**: Next.js 15 (App Router)
- **Styling**: Tailwind CSS v4, Framer Motion for animations
- **Components**: shadcn/ui (Radix UI primitives)
- **Architecture**: Acts as a BFF (Backend-For-Frontend). Uses React state and `EventSource` (SSE) to display live backend scraping progress.

### Backend (`/backend`)
- **Framework**: FastAPI, Uvicorn
- **Architecture**: Modular Services. The core logic is split into focused modules inside `backend/core/` (scraper, extractor, embedder, vector_store, resume_parser, advisor, orchestrator).
- **LLM Routing**: Separates heavy reasoning (`ADVISOR_MODEL`) from fast, concurrent JSON extraction (`EXTRACTOR_MODEL`).
- **Vector Database**: Qdrant (running via Docker).
- **Scraping Engine**: LinkedIn MCP Server (`stickerdaniel/linkedin-mcp-server`) spawned natively in the background via `uvx` and `stdio`.

## 3. Workflows

### A. Concurrent Live Scraping Workflow
1. User configures filters (Keywords, Location, Date Posted) in the UI and clicks "Start Live Scraping".
2. The UI opens a Server-Sent Events (SSE) connection to `POST /api/v1/scrape/stream`.
3. The `JobMatcherOrchestrator` invokes the `LinkedInMCPScraper` via `stdio` to retrieve raw job IDs.
4. An `asyncio.Queue` and `asyncio.Semaphore` process the jobs concurrently (up to 3 at a time for cloud LLMs).
5. For each job:
   - Fetches full job posting details via MCP.
   - `LLMJobExtractor` uses the `EXTRACTOR_MODEL` to output structured JSON.
   - `UniversalEmbedder` creates a dense vector representation.
   - `QdrantVectorStore` upserts the job into the database safely.
6. Progress events (e.g., `[fetching]`, `[extracting]`) are yielded back to the frontend in real-time.

### B. Resume Matching Workflow
1. User uploads a PDF resume on the Next.js frontend.
2. The `PDFResumeParser` reads the raw text, injects the current date into the prompt, and uses the `ADVISOR_MODEL` to extract a structured `ResumeProfile`.
3. The profile is embedded and `QdrantVectorStore` performs a cosine similarity search against scraped jobs.
4. The top-K matched jobs are returned to the frontend and displayed.

### C. Resume Advice Workflow
1. User clicks "Get Advice" on a specific matched job.
2. `LLMResumeAdvisor` uses the `ADVISOR_MODEL` to compare the structured resume and the job posting.
3. The LLM generates actionable advice (Summary tweaks, Skills to add, Experience gaps) which is rendered in a slide-over panel.

## 4. How to Run from Scratch

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop) (for Qdrant)
- [Node.js](https://nodejs.org/en) (v18+)
- Python 3.12+
- `uv` package manager (`pip install uv`)

### Step 1: Start Qdrant Vector DB
```bash
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
```

### Step 2: Login to LinkedIn MCP
The backend will automatically spawn the MCP server for you, but you must authenticate it with your LinkedIn account first. Run this once:
```bash
uvx mcp-server-linkedin@latest --login
```
*(Follow the CLI prompts to log into your LinkedIn account. Session cookies will be saved locally.)*

### Step 3: Configure Environment Variables
Copy the example environment file and configure your LLM providers.

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env`. You can choose your provider (`openai`, `gemini`, `huggingface`, or `ollama`):
| Variable | Example Value | Description |
|----------|---------------|-------------|
| `LLM_PROVIDER` | `gemini` | `ollama`, `openai`, `gemini`, or `huggingface` |
| `ADVISOR_MODEL` | `google/gemma-3-12b-it:featherless` | The heavy reasoning model (12B+) |
| `EXTRACTOR_MODEL`| `google/gemma-3-4b-it:featherless` | The fast, lightweight JSON extraction model (4B-8B) |
| `EMBED_MODEL`| `text-embedding-004`| The embedding model name |
| `EMBED_DIM` | `768` | Vector dimension of the embed model |
| `GEMINI_API_KEY` | `AIza...` | Needed if provider is gemini |
| `OPENAI_API_KEY` | `sk-...` | Needed if provider is openai |
| `HF_TOKEN` | `hf_...` | Needed if provider is huggingface |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Used only if provider is `ollama` |

### Step 4: Run the Backend
```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Unix: source venv/bin/activate
pip install -r requirements.txt

# Start the FastAPI server
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```
*(Note: Do not run a separate MCP HTTP server! The backend spawns it automatically via `stdio`.)*

### Step 5: Run the Frontend
Open a new terminal window:
```bash
cd frontend_v2
npm install
npm run dev
```
Open your browser to `http://localhost:3000` to access the dashboard!

## 5. Acknowledgements & Open Source
This project leverages the power of the **Model Context Protocol (MCP)** to interact safely and efficiently with LinkedIn's platform. Specifically, it utilizes the [LinkedIn MCP Server](https://github.com/stickerdaniel/linkedin-mcp-server) by @stickerdaniel. 

By separating the complex scraping and session management logic into the MCP server, our backend focuses entirely on AI orchestration and similarity matching.
