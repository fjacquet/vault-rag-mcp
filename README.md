# vault-rag-mcp

[![CI](https://github.com/fjacquet/vault-rag-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/fjacquet/vault-rag-mcp/actions/workflows/ci.yml)

MCP server for semantic search in an Obsidian Second Brain vault, using a self-hosted Qdrant vector store and Google Gemini embeddings.

## Architecture

```
Claude Code <-> vault-rag MCP server (stdio)
                 |-> Google Gemini gemini-embedding-001 (native 3072d)
                 |-> Qdrant `vault_chunks` collection (3072d, Cosine distance)
```

Part of a hybrid RAG architecture:
- **Indexation**: n8n (remote) + Google Gemini API
- **Local queries**: This MCP server + Google Gemini API
- **Web chat**: n8n Vault Chat (AI Agent + Gemini native) or Chat Hub (HTTP pipeline)
- **Bulk index**: Script using Gemini `gemini-embedding-001`

Same model (`gemini-embedding-001`, native 3072d) everywhere ensures vector compatibility.
Vectors are stored at native 3072 dimensions (float32) with Cosine distance.

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
- Qdrant instance with a `vault_chunks` collection (created automatically on first index)

## Setup

```bash
# Clone and install
cd ~/Projects/vault-rag-mcp
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your Google API key and Qdrant credentials
```

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `QDRANT_URL` | Qdrant instance URL (HTTPS requires the `:443` port; appended automatically if missing) | (required) |
| `QDRANT_API_KEY` | Qdrant API key | (required) |
| `GOOGLE_API_KEY` | Google AI API key | (required) |
| `EMBEDDING_MODEL` | Gemini embedding model | `gemini-embedding-001` |

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
        "QDRANT_URL": "https://your-qdrant-instance.example.com",
        "QDRANT_API_KEY": "your-qdrant-api-key",
        "GOOGLE_API_KEY": "your-google-api-key",
        "EMBEDDING_MODEL": "gemini-embedding-001"
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
5. Upserts to Qdrant with a SHA256 file_hash payload for incremental re-runs

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
│       └── qdrant_store.py     # Qdrant client + collection operations
├── scripts/
│   └── bulk_index.py           # Bulk indexation via Google Gemini
└── n8n-workflows/              # n8n workflow definitions
    ├── vault-rag-github-indexation.json
    └── vault-rag-chat-hub.json
```

## Qdrant collection

Collection `vault_chunks` — vectors at 3072 dimensions, Cosine distance. Each point carries:
- `content` — chunk text
- `file_path` — relative path from vault root
- `chunk_index` — position within file
- `para_folder` — PARA folder (1_Projects, 2_Areas, etc.)
- `note_type` — frontmatter type (memo, glossary, howto, etc.)
- `file_hash` — SHA256 for change detection
- `metadata` — tags, type, para_folder

Point IDs are deterministic UUID5 values derived from `file_path::chunk_index`.

Payload indexes: `file_path` (keyword), `para_folder` (keyword), `note_type` (keyword), `chunk_index` (integer).

## Tech stack

- **MCP SDK**: `mcp[cli]` with `FastMCP` (stdio transport)
- **Embeddings**: Google Gemini `gemini-embedding-001` via the `google-genai` SDK (native 3072d, multilingual, 2048 token/text)
- **Vector DB**: Qdrant (self-hosted) — `vault_chunks` collection, 3072d Cosine distance
- **Build**: uv + hatch
