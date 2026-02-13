"""MCP server for semantic search in the Second Brain vault.

Exposes 3 tools:
- search_vault: semantic search across the entire vault
- search_glossary: search within glossary definitions only
- get_note: retrieve full content of a specific note
"""

from mcp.server.fastmcp import FastMCP

from . import supabase_client
from .embeddings import get_embedding

mcp = FastMCP(
    name="vault-rag",
    instructions="Semantic search in an Obsidian Second Brain vault. "
    "Use search_vault for general queries, search_glossary for term definitions, "
    "and get_note to retrieve a specific note by file path.",
)


def _format_result(r: dict) -> str:
    """Format a search result for display."""
    similarity = r.get("similarity", 0)
    file_path = r.get("file_path", "unknown")
    para_folder = r.get("para_folder", "")
    note_type = r.get("note_type", "")
    content = r.get("content", "")
    # Truncate long content for readability
    if len(content) > 500:
        content = content[:500] + "..."
    return (
        f"[{similarity:.3f}] {file_path} ({para_folder}/{note_type})\n"
        f"{content}\n"
    )


@mcp.tool()
def search_vault(
    query: str,
    limit: int = 10,
    para_folder: str | None = None,
    note_type: str | None = None,
) -> str:
    """Search the vault semantically. Returns the most relevant notes.

    Args:
        query: Natural language search query (works in French and English)
        limit: Maximum number of results (default 10)
        para_folder: Filter by PARA folder (1_Projects, 2_Areas, 3_Resources, 4_Archives)
        note_type: Filter by note type (memo, glossary, howto, meeting-note, etc.)
    """
    embedding = get_embedding(query, task_type="RETRIEVAL_QUERY")
    results = supabase_client.search_vault(
        query_embedding=embedding,
        match_count=limit,
        filter_para_folder=para_folder,
        filter_note_type=note_type,
    )
    if not results:
        return "No results found."
    return "\n---\n".join(_format_result(r) for r in results)


@mcp.tool()
def search_glossary(query: str, limit: int = 5) -> str:
    """Search the glossary (1878 term definitions in 3_Resources/definitions/).

    Args:
        query: Term or concept to look up (works in French and English)
        limit: Maximum number of results (default 5)
    """
    embedding = get_embedding(query, task_type="RETRIEVAL_QUERY")
    results = supabase_client.search_vault(
        query_embedding=embedding,
        match_count=limit,
        filter_para_folder="3_Resources",
        filter_note_type="glossary",
    )
    if not results:
        return "No glossary entries found."
    return "\n---\n".join(_format_result(r) for r in results)


@mcp.tool()
def get_note(file_path: str) -> str:
    """Retrieve the full content of a specific note by its file path.

    Args:
        file_path: Path relative to vault root (e.g. '3_Resources/definitions/p/powerflex.md')
    """
    chunks = supabase_client.get_note_chunks(file_path)
    if not chunks:
        return f"Note not found: {file_path}"
    return "\n\n".join(c["content"] for c in chunks)


def main():
    """Entry point for the MCP server (stdio transport)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
