# LinkedIn Job Matcher - Complete Project Information

This document serves as the comprehensive source of truth for the LinkedIn Job Matcher project, covering the architecture, workflows, setup, and configurations.

## 1. Project Overview

LinkedIn Job Matcher is a modular, AI-powered system that automates the process of finding relevant jobs on LinkedIn, matching them against your specific resume, and generating tailored advice to improve your chances of landing an interview.

It achieves this by combining:
- **Model Context Protocol (MCP)** for reliable LinkedIn data extraction.
- **Local Large Language Models (Ollama / Gemma)** for structured field extraction and resume advice.
- **Local Vector Database (Qdrant)** for semantic similarity search.
- **FastAPI** for backend orchestration.
- **Next.js (App Router)** for a modern, responsive frontend dashboard.

## 2. Architecture & Tech Stack

### Frontend (`/frontend_v2`)
- **Framework**: Next.js 15 (App Router)
- **Styling**: Tailwind CSS v4, Framer Motion for animations
- **Components**: shadcn/ui (Radix UI primitives)
- **Icons**: Lucide React
- **Architecture**: Acts as a BFF (Backend-For-Frontend). API routes in Next.js (`/api/match`, `/api/advise`) receive `FormData` from the browser and proxy the requests to the Python FastAPI backend.

### Backend (`/backend`)
- **Framework**: FastAPI, Uvicorn
- **Architecture**: Modular Monolith (non-SOLID). The core logic is split into focused modules inside `backend/core/` (models, scraper, extractor, embedder, vector_store, resume_parser, advisor, orchestrator).
- **LLM Engine**: Ollama (running locally), wrapping models like `gemma3:4b`.
- **Embeddings**: Ollama (`nomic-embed-text:v1.5`).
- **Vector Database**: Qdrant (running via Docker).
- **Scraping Engine**: LinkedIn MCP Server (`https://github.com/stickerdaniel/linkedin-mcp-server`) consumed via `langchain-mcp-adapters`.
- **PDF Parsing**: `pdfplumber` with fallback to `PyPDF2`.

## 3. Workflows

### A. Job Scraping Workflow
1. User or Cron triggers the `scrape_jobs` API.
2. The `JobMatcherOrchestrator` invokes the `LinkedInMCPScraper` with a search query.
3. The scraper communicates with the MCP server to retrieve raw job IDs and subsequently fetches full job posting details.
4. Raw job text is passed to the `LLMJobExtractor` which uses the local LLM to output structured JSON (Title, Company, Skills, Salary, etc.).
5. The `OllamaEmbedder` creates a dense vector representation of the job posting.
6. The `QdrantVectorStore` upserts the job into the database with a deterministic ID (`uuid5`) to ensure idempotency (no duplicates).

### B. Resume Matching Workflow
1. User uploads a PDF resume on the Next.js frontend.
2. The frontend proxies the PDF to the FastAPI `/api/v1/match` endpoint.
3. The `PDFResumeParser` reads the raw text and uses the LLM to extract a structured `ResumeProfile` (Skills, Experience, Target Roles).
4. The resume profile is embedded into a vector.
5. `QdrantVectorStore` performs a cosine similarity search against the previously scraped jobs.
6. The top-K matched jobs, along with similarity scores, are returned to the frontend and displayed in the UI.

### C. Resume Advice Workflow
1. User clicks "Get Advice" on a specific matched job in the frontend.
2. Frontend proxies the request to FastAPI `/api/v1/advise`, sending the resume and the target `job_id`.
3. `LLMResumeAdvisor` retrieves both the structured resume and the structured job posting.
4. The local LLM compares them and generates actionable advice (Summary tweaks, Skills to add/emphasize, Experience gaps).
5. The advice is rendered in a slide-over panel on the frontend.

## 4. Setup & Configuration

### Prerequisites
- Docker (for Qdrant)
- Ollama installed locally
- Node.js (v18+)
- Python 3.12+
- `uvx` (Astral's UV tool for running the MCP server)

### Step 1: Start External Services

```bash
# 1. Start Qdrant Vector DB
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant

# 2. Start Ollama and pull models
ollama serve
ollama pull nomic-embed-text:v1.5
ollama pull gemma3:4b

# 3. Start LinkedIn MCP Server
# NOTE: Requires login first!
uvx mcp-server-linkedin@latest --login
uvx mcp-server-linkedin@latest --transport streamable-http --host 127.0.0.1 --port 8080 --path /mcp
```

### Step 2: Configure Environment Variables

The project uses `python-dotenv` to manage configurations. We provide a `backend/.env.example` template. You must copy it to `backend/.env` and configure your chosen provider.

```bash
cp backend/.env.example backend/.env
```

Inside `.env`, you can choose your LLM provider by setting `LLM_PROVIDER`. The backend supports **ollama**, **openai**, **gemini**, and **huggingface** natively using OpenAI-compatible endpoints.

| Variable | Example Value | Description |
|----------|---------------|-------------|
| `LLM_PROVIDER` | `gemini` | `ollama`, `openai`, `gemini`, or `huggingface` |
| `OPENAI_API_KEY` | `sk-...` | Needed if provider is openai |
| `GEMINI_API_KEY` | `AIza...` | Needed if provider is gemini |
| `HF_TOKEN` | `hf_...` | Needed if provider is huggingface |
| `LLM_MODEL` | `gemini-2.5-flash` | The extraction/advice model name |
| `EMBED_MODEL`| `text-embedding-004`| The embedding model name |
| `EMBED_DIM` | `768` | Vector dimension of the embed model |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Used only if provider is `ollama` |
| `EMBED_BASE_URL`| `http://localhost:11434/v1` | Used only if provider is `ollama` |
| `QDRANT_URL` | `http://localhost:6333` | Vector DB endpoint |
| `QDRANT_COLLECTION`| `linkedin_jobs` | Qdrant Collection name |
| `MCP_LINKEDIN_URL` | `http://localhost:8080/mcp` | MCP server endpoint |

In the `frontend_v2` directory:
| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_URL` | `http://127.0.0.1:8000` | Points to FastAPI server |

### Step 3: Run the Backend

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Unix: source venv/bin/activate
pip install -r requirements.txt

# Start the FastAPI server
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

### Step 4: Run the Frontend

```bash
cd frontend_v2
npm install
npm run dev
# Dashboard available at http://localhost:3000
```

## 5. Acknowledgements & Open Source
This project leverages the power of the **Model Context Protocol (MCP)** to interact safely and efficiently with LinkedIn's platform. Specifically, it utilizes the [LinkedIn MCP Server](https://github.com/stickerdaniel/linkedin-mcp-server) by @stickerdaniel. 

By separating the complex scraping and session management logic into the MCP server, our backend focuses entirely on AI orchestration and similarity matching.
