# vault-rag-mcp

MCP server for semantic search in an Obsidian Second Brain vault, using Supabase pgvector and local Ollama embeddings.

## Architecture

```
Claude Code <-> vault-rag MCP server (stdio)
                 |-> Ollama nomic-embed-text (768d, local)
                 |-> Supabase pgvector cosine similarity
```

Part of a hybrid RAG architecture:
- **Indexation**: n8n (remote) + OpenRouter `nomic-ai/nomic-embed-text`
- **Local queries**: This MCP server + Ollama `nomic-embed-text`
- **Web chat**: n8n Chat Hub + OpenRouter embed + LLM

Same model (`nomic-embed-text`, 768d) everywhere ensures vector compatibility.

## Tools

| Tool | Description |
|------|-------------|
| `search_vault` | Semantic search across the entire vault (query, limit, para_folder, note_type) |
| `search_glossary` | Search within glossary definitions (3_Resources/definitions/) |
| `get_note` | Retrieve full content of a note by file path |

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- [Ollama](https://ollama.com/) with `nomic-embed-text` model pulled
- Supabase project with `vault_chunks` table and pgvector

```bash
ollama pull nomic-embed-text
```

## Setup

```bash
# Clone and install
cd ~/Projects/vault-rag-mcp
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your Supabase credentials
```

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPABASE_URL` | Supabase project URL | (required) |
| `SUPABASE_KEY` | Supabase anon key | (required) |
| `OLLAMA_HOST` | Ollama API endpoint | `http://localhost:11434` |
| `OLLAMA_MODEL` | Embedding model name | `nomic-embed-text` |

## Usage

### As MCP server (Claude Code)

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "vault-rag": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vault-rag-mcp", "vault-rag-mcp"],
      "env": {
        "SUPABASE_URL": "https://your-project.supabase.co",
        "SUPABASE_KEY": "your-anon-key",
        "OLLAMA_HOST": "http://localhost:11434",
        "OLLAMA_MODEL": "nomic-embed-text"
      }
    }
  }
}
```

Restart Claude Code to activate. Then use the tools directly in conversation.

### Bulk indexation

One-time script to index an entire Obsidian vault via local Ollama:

```bash
uv run python scripts/bulk_index.py /path/to/vault
```

Options:
- `--force` : Re-index all files, ignoring file_hash cache

The script:
1. Walks the vault, skips `.obsidian/`, `templates/`, `.trash/`, files > 500 KB
2. Parses YAML frontmatter (type, tags, PARA folder)
3. Chunks by H2 sections, splits oversized chunks (> 6000 chars)
4. Embeds via Ollama in batches of 20
5. Upserts to Supabase with SHA256 file_hash for incremental re-runs

After initial bulk indexation, incremental updates are handled by n8n via OpenRouter.

## Project structure

```
vault-rag-mcp/
├── pyproject.toml              # uv + hatch build config
├── .env.example                # Environment template
├── src/
│   └── vault_rag_mcp/
│       ├── __init__.py
│       ├── server.py           # MCP server (FastMCP, stdio) — 3 tools
│       ├── embeddings.py       # Ollama embedding client
│       └── supabase_client.py  # Supabase CRUD + RPC calls
└── scripts/
    └── bulk_index.py           # Bulk indexation via Ollama
```

## Supabase schema

Table `vault_chunks` with:
- `content TEXT` — chunk text
- `embedding VECTOR(768)` — nomic-embed-text vector
- `metadata JSONB` — tags, type, para_folder
- `file_path TEXT` — relative path from vault root
- `chunk_index INTEGER` — position within file
- `para_folder TEXT` — PARA folder (1_Projects, 2_Areas, etc.)
- `note_type TEXT` — frontmatter type (memo, glossary, howto, etc.)
- `file_hash TEXT` — SHA256 for change detection

RPC functions: `search_vault()`, `delete_file_chunks()`

## Tech stack

- **MCP SDK**: `mcp[cli]` with `FastMCP` (stdio transport)
- **Embeddings**: Ollama `nomic-embed-text` (768d, multilingual, 8192 token context)
- **Vector DB**: Supabase PostgreSQL + pgvector (HNSW cosine index)
- **Build**: uv + hatch
