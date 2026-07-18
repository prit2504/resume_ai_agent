# LinkedIn Job Matcher — AI-Powered Career Assistant

## Overview

A fully modular, AI-native system that:
1. **Scrapes** LinkedIn jobs via the [LinkedIn MCP Server](https://github.com/stickerdaniel/linkedin-mcp-server).
2. **Streams** live scraping progress directly to the frontend using Server-Sent Events (SSE).
3. **Extracts** structured fields concurrently using a lightweight local/cloud LLM (`EXTRACTOR_MODEL`).
4. **Embeds** job descriptions into a vector space.
5. **Stores** everything in Qdrant with idempotent upserts.
6. **Parses** user resumes (PDF) and extracts structured profiles.
7. **Matches** resumes to jobs via semantic similarity search.
8. **Advises** users on resume improvements using a heavy reasoning LLM (`ADVISOR_MODEL`).
9. **Serves** everything through a beautiful Next.js dashboard.

## Architecture

The project has transitioned into a highly modular, multi-provider architecture designed for maximum performance through asyncio concurrency and streaming.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                              NEXT.JS FRONTEND                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ Resume       │  │ Job Match    │  │ Live Scrape  │  │ AI Advisor       │ │
│  │ Upload       │  │ Cards        │  │ Loader (SSE) │  │ Slide-over       │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────┘ │
└──────────────────────────────┬─────────────▲────────────────────────────────┘
                     HTTP/REST │             │ Server-Sent Events (Live)
┌──────────────────────────────▼─────────────┴────────────────────────────────┐
│                           FASTAPI MICROSERVICE                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     JobMatcherOrchestrator                           │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌──────────────┐ ┌─────────────┐  ┌───────────┐    │   │
│  │  │ Scraper     │  │ Extractor    │ │ Embedder    │  │VectorStore│    │   │
│  │  │ (stdio MCP) │  │ (Gemma 4B)   │ │ (Universal) │  │ Qdrant    │    │   │
│  │  └──────┬──────┘  └──────┬───────┘ └──────┬──────┘  └───────────┘    │   │
│  │         └────────────────┴───────┬────────┘                          │   │
│  │                           asyncio.gather (x3 Concurrency)            │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌──────────────┐                                   │   │
│  │  │ResumeParser │  │ResumeAdvisor │                                   │   │
│  │  │ PDF + LLM   │  │ (Gemma 12B)  │                                   │   │
│  │  └─────────────┘  └──────────────┘                                   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────────┘
                  MCP Protocol │ (stdio)
┌──────────────────────────────▼──────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                                   │
│  ┌─────────────────┐ ┌───────────────┐ ┌─────────────┐ ┌────────────────┐   │
│  │ LinkedIn        │ │ Cloud LLMs    │ │ Qdrant      │ │ Local LLMs     │   │
│  │ uvx mcp-server  │ │ OpenAI/Gemini │ │ Vector DB   │ │ Ollama/LMStudio│   │
│  └─────────────────┘ └───────────────┘ └─────────────┘ └────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## File Structure

```text
job-matcher/
├── backend/
│   ├── core/                     # Modular backend services
│   │   ├── models.py             # Data classes and Enums
│   │   ├── scraper.py            # LinkedIn MCP Scraper (stdio)
│   │   ├── extractor.py          # LLM JSON Extraction
│   │   ├── embedder.py           # Universal Embedder
│   │   ├── vector_store.py       # Qdrant Vector Store
│   │   ├── resume_parser.py      # PDF Resume Parser (Date aware)
│   │   ├── advisor.py            # AI Resume Advisor
│   │   └── orchestrator.py       # Orchestrator (SSE & Async Queues)
│   ├── api.py                    # FastAPI REST & SSE endpoints
│   ├── .env                      # Multi-provider LLM Configuration
│   └── requirements.txt          # Python deps
│
├── frontend_v2/
│   ├── app/                      # Next.js App Router
│   │   ├── api/                  # API routes (BFF)
│   │   ├── globals.css           # Tailwind CSS
│   │   └── page.tsx              # Main dashboard with Live UI
│   └── package.json
│
├── info.md                       # Complete Project Documentation
└── README.md
```

## Setup & Quick Start

For a detailed setup guide, including all configuration variables and workflows, please read the [info.md](./info.md) file in the root of this project.

### Briefly:
1. **Database:** Start Qdrant (`docker run -p 6333:6333 qdrant/qdrant`)
2. **Environment:** Copy `backend/.env.example` to `backend/.env` and configure your API keys (OpenAI, Gemini, HuggingFace) or leave it pointing to local Ollama.
3. **Backend:** Start FastAPI (`cd backend && uvicorn api:app --port 8000`). *Note: FastAPI will automatically spawn the LinkedIn MCP server using `uvx`.*
4. **Frontend:** Start Next.js (`cd frontend_v2 && npm run dev`)

## Acknowledgments & Open Source Contributions

This project relies on the **Model Context Protocol (MCP)** to interact securely and safely with LinkedIn, specifically using the excellent [LinkedIn MCP Server](https://github.com/stickerdaniel/linkedin-mcp-server) created by [stickerdaniel](https://github.com/stickerdaniel). 

I plan to contribute to this open-source MCP server to continue improving its capabilities for the community!

## License

MIT License
