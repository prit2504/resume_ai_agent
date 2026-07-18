# LinkedIn Job Matcher — AI-Powered Career Assistant

## Overview

A fully modular, AI-native system that:
1. **Scrapes** LinkedIn jobs via the [LinkedIn MCP Server](https://github.com/stickerdaniel/linkedin-mcp-server).
2. **Extracts** structured fields using a local LLM (`gemma3:4b`).
3. **Embeds** job descriptions into a vector space (`nomic-embed-text`).
4. **Stores** everything in Qdrant with idempotent upserts.
5. **Parses** user resumes (PDF) and extracts structured profiles.
6. **Matches** resumes to jobs via semantic similarity search.
7. **Advises** users on resume improvements using AI.
8. **Serves** everything through a beautiful Next.js dashboard.

## Architecture

The project recently transitioned from a complex, SOLID-principled monolith into a streamlined, highly modular architecture to improve maintainability and developer experience.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                              NEXT.JS FRONTEND                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Resume       │  │ Job Match    │  │ AI Advisor   │  │ Analytics        │  │
│  │ Upload       │  │ Cards        │  │ Slide-over   │  │ Dashboard        │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ HTTP/REST
┌──────────────────────────────▼──────────────────────────────────────────────┐
│                           FASTAPI MICROSERVICE                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     JobMatcherOrchestrator                           │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │   │
│  │  │ Scraper     │  │ Extractor   │  │ Embedder    │  │VectorStore│ │   │
│  │  │ LinkedInMCP │  │ LLM (gemma) │  │ OllamaEmbed │  │ Qdrant    │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘ │   │
│  │  ┌─────────────┐  ┌─────────────┐                                  │   │
│  │  │ResumeParser │  │ResumeAdvisor│                                  │   │
│  │  │ PDF + LLM   │  │ LLM Compare │                                  │   │
│  │  └─────────────┘  └─────────────┘                                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                               │ MCP Protocol
┌──────────────────────────────▼──────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ LinkedIn    │  │ Ollama      │  │ Qdrant      │  │ Local LLM           │  │
│  │ MCP Server  │  │ Embeddings  │  │ Vector DB   │  │ (gemma3:4b)         │  │
│  │ :8080/mcp   │  │ :11434/v1   │  │ :6333       │  │ :11434/v1           │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## File Structure

```text
job-matcher/
├── backend/
│   ├── core/                     # Modular backend services
│   │   ├── models.py             # Data classes and Enums
│   │   ├── scraper.py            # LinkedIn MCP Scraper
│   │   ├── extractor.py          # LLM JSON Extraction
│   │   ├── embedder.py           # Ollama Embedder
│   │   ├── vector_store.py       # Qdrant Vector Store
│   │   ├── resume_parser.py      # PDF Resume Parser
│   │   ├── advisor.py            # AI Resume Advisor
│   │   └── orchestrator.py       # Job Matcher Orchestrator
│   ├── job_matcher_backend.py    # Legacy SOLID monolith (preserved)
│   ├── api.py                    # FastAPI REST wrapper
│   └── requirements.txt          # Python deps
│
├── frontend_v2/
│   ├── app/                      # Next.js App Router
│   │   ├── api/                  # API routes (BFF)
│   │   ├── globals.css           # Tailwind CSS
│   │   └── page.tsx              # Main dashboard
│   └── package.json
│
├── info.md                       # Complete Project Documentation
└── README.md
```

## Setup & Quick Start

For a detailed setup guide, including all configuration variables and workflows, please read the [info.md](./info.md) file in the root of this project.

### Briefly:
1. Start Qdrant (`docker run -p 6333:6333 qdrant/qdrant`)
2. Start Ollama (`ollama serve`)
3. Start the LinkedIn MCP Server (`uvx mcp-server-linkedin@latest --transport streamable-http --port 8080`)
4. Start FastAPI (`cd backend && uvicorn api:app --port 8000`)
5. Start Next.js (`cd frontend_v2 && npm run dev`)

## Acknowledgments & Open Source Contributions

This project relies on the **Model Context Protocol (MCP)** to interact securely and safely with LinkedIn, specifically using the excellent [LinkedIn MCP Server](https://github.com/stickerdaniel/linkedin-mcp-server) created by [stickerdaniel](https://github.com/stickerdaniel). 

I plan to contribute to this open-source MCP server to continue improving its capabilities for the community!

## License

MIT
