# vault-rag-mcp

MCP server for semantic search in an Obsidian Second Brain vault, using Supabase pgvector and Google Gemini embeddings.

## Architecture

```
Claude Code <-> vault-rag MCP server (stdio)
                 |-> Google Gemini gemini-embedding-001 (native 3072d)
                 |-> Supabase pgvector halfvec cosine similarity
```

Part of a hybrid RAG architecture:
- **Indexation**: n8n (remote) + Google Gemini API
- **Local queries**: This MCP server + Google Gemini API
- **Web chat**: n8n Vault Chat (AI Agent + Gemini native) or Chat Hub (HTTP pipeline)
- **Bulk index**: Script using Gemini `gemini-embedding-001`

Same model (`gemini-embedding-001`, native 3072d) everywhere ensures vector compatibility.
Storage optimized with `halfvec` (float16) — full quality at half the storage (~284 MB vs ~567 MB).

Asymmetric task types: `RETRIEVAL_DOCUMENT` for indexing, `RETRIEVAL_QUERY` for search.

## Tools

| Tool | Description |
|------|-------------|
| `search_vault` | Semantic search across the entire vault (query, limit, para_folder, note_type) |
| `search_glossary` | Search within glossary definitions (3_Resources/definitions/) |
| `get_note` | Retrieve full content of a note by file path |

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- Google API key (for Gemini embeddings)
- Supabase project with `vault_chunks` table and pgvector

## Setup

```bash
# Clone and install
cd ~/Projects/vault-rag-mcp
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your Google API key and Supabase credentials
```

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPABASE_URL` | Supabase project URL | (required) |
| `SUPABASE_KEY` | Supabase anon key | (required) |
| `GOOGLE_API_KEY` | Google AI API key | (required) |
| `EMBEDDING_MODEL` | Gemini embedding model | `gemini-embedding-001` |
| `EMBEDDING_DIMENSIONS` | Output dimensions (native=3072) | `3072` |

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
        "GOOGLE_API_KEY": "your-google-api-key",
        "EMBEDDING_MODEL": "gemini-embedding-001",
        "EMBEDDING_DIMENSIONS": "3072"
      }
    }
  }
}
```

Restart Claude Code to activate. Then use the tools directly in conversation.

### Bulk indexation

Script to index an entire Obsidian vault via Google Gemini:

```bash
uv run python scripts/bulk_index.py /path/to/vault [--force]
```

Options:
- `--force` : Re-index all files, ignoring file_hash cache

The script:
1. Walks the vault, skips `.obsidian/`, `templates/`, `.trash/`, files > 500 KB
2. Parses YAML frontmatter (type, tags, PARA folder)
3. Chunks by H2 sections, splits oversized chunks (> 2000 chars)
4. Embeds via Google Gemini in batches of 50 (task_type=RETRIEVAL_DOCUMENT)
5. Upserts to Supabase with SHA256 file_hash for incremental re-runs

After initial bulk indexation, incremental updates are handled by n8n via Gemini API.

## Project structure

```
vault-rag-mcp/
├── pyproject.toml              # uv + hatch build config
├── .env.example                # Environment template
├── src/
│   └── vault_rag_mcp/
│       ├── __init__.py
│       ├── server.py           # MCP server (FastMCP, stdio) — 3 tools
│       ├── embeddings.py       # Google Gemini embedding client (native 3072d)
│       └── supabase_client.py  # Supabase CRUD + RPC calls
├── scripts/
│   └── bulk_index.py           # Bulk indexation via Google Gemini
└── n8n-workflows/              # n8n workflow definitions
    ├── vault-rag-github-indexation.json
    └── vault-rag-chat-hub.json
```

## Supabase schema

Table `vault_chunks` with:
- `content TEXT` — chunk text
- `embedding HALFVEC(3072)` — gemini-embedding-001 vector (float16, half storage)
- `metadata JSONB` — tags, type, para_folder
- `file_path TEXT` — relative path from vault root
- `chunk_index INTEGER` — position within file
- `para_folder TEXT` — PARA folder (1_Projects, 2_Areas, etc.)
- `note_type TEXT` — frontmatter type (memo, glossary, howto, etc.)
- `file_hash TEXT` — SHA256 for change detection

RPC functions: `search_vault()`, `match_vault_chunks()`, `delete_file_chunks()`

## Tech stack

- **MCP SDK**: `mcp[cli]` with `FastMCP` (stdio transport)
- **Embeddings**: Google Gemini `gemini-embedding-001` (native 3072d, multilingual, 2048 token/text)
- **Vector DB**: Supabase PostgreSQL + pgvector 0.8.0 (HNSW cosine, halfvec storage)
- **Build**: uv + hatch
