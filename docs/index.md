# vault-rag-mcp

An [MCP](https://modelcontextprotocol.io/) server that provides semantic search
over an Obsidian "Second Brain" vault. It embeds queries with Google Gemini
(`gemini-embedding-001`, native 3072d) and retrieves the most relevant note
chunks from a [Qdrant](https://qdrant.tech/) collection (`vault_chunks`).

The server runs over stdio and is consumed by Claude Code (or any MCP client).

## Tools

The server exposes three tools:

### `search_vault`

Semantic search across the entire vault. Returns the most relevant notes for a
natural-language query (works in French and English).

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | `str` | Natural-language search query |
| `limit` | `int` | Maximum number of results (default `10`) |
| `para_folder` | `str \| None` | Filter by PARA folder (`1_Projects`, `2_Areas`, `3_Resources`, `4_Archives`) |
| `note_type` | `str \| None` | Filter by note type (`memo`, `glossary`, `howto`, …) |

### `search_glossary`

Search only within the glossary definitions stored under
`3_Resources/definitions/`. A focused variant of `search_vault` for looking up
term and acronym definitions.

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | `str` | Term or concept to look up |
| `limit` | `int` | Maximum number of results (default `5`) |

### `get_note`

Retrieve the full content of a specific note by its vault-relative file path
(e.g. `3_Resources/definitions/p/powerflex.md`).

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_path` | `str` | Path relative to the vault root |

## Architecture

```text
Claude Code  <->  vault-rag MCP server (stdio)
                    |-> Google Gemini gemini-embedding-001 (native 3072d)
                    |-> Qdrant vault_chunks (Cosine similarity)
```

The same embedding model is used for both indexing (`RETRIEVAL_DOCUMENT`) and
search (`RETRIEVAL_QUERY`), ensuring vector compatibility across the pipeline.

## Development

```bash
make tools     # uv sync (install deps + dev/docs groups)
make lint      # ruff check + format --check
make test      # pytest with coverage
make docs      # mkdocs build --strict
make security  # semgrep (advisory)
```
