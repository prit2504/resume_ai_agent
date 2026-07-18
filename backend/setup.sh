#!/bin/bash
# Job Matcher — Setup Script
# ===========================

set -e

echo "🚀 Setting up LinkedIn Job Matcher..."

# 1. Python Backend
echo "📦 Installing Python dependencies..."
python -m pip install -r requirements.txt

# 2. Start infrastructure
echo "🐳 Starting Qdrant (Docker)..."
docker run -d --name qdrant -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant || echo "Qdrant already running"

echo "🦙 Starting Ollama (ensure it's installed)..."
ollama pull nomic-embed-text:v1.5 || true
ollama pull gemma3:4b || true

echo "🔗 Starting LinkedIn MCP Server..."
# Run in background or separate terminal:
# uvx mcp-server-linkedin@latest --login
# uvx mcp-server-linkedin@latest --transport streamable-http --host 127.0.0.1 --port 8080 --path /mcp

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Login to LinkedIn MCP: uvx mcp-server-linkedin@latest --login"
echo "  2. Start MCP server: uvx mcp-server-linkedin@latest --transport streamable-http --host 127.0.0.1 --port 8080 --path /mcp"
echo "  3. Scrape jobs: python -m job_matcher_backend scrape -k 'AI Engineer' -l 'Remote'"
echo "  4. Match resume: python -m job_matcher_backend match --resume resume.pdf"
echo "  5. Start API: uvicorn api:app --host 0.0.0.0 --port 8000"
echo "  6. Start UI: cd job-matcher-ui && npm run dev"
