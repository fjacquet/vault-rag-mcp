"""Supabase client for vault_chunks operations."""

import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    """Get or create Supabase client singleton."""
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        _client = create_client(url, key)
    return _client


def search_vault(
    query_embedding: list[float],
    match_count: int = 10,
    filter_para_folder: str | None = None,
    filter_note_type: str | None = None,
) -> list[dict]:
    """Semantic search via Supabase RPC."""
    client = get_client()
    result = client.rpc(
        "search_vault",
        {
            "query_embedding": query_embedding,
            "match_count": match_count,
            "filter_para_folder": filter_para_folder,
            "filter_note_type": filter_note_type,
        },
    ).execute()
    return result.data


def get_note_chunks(file_path: str) -> list[dict]:
    """Get all chunks for a file path, ordered by chunk_index."""
    client = get_client()
    result = (
        client.table("vault_chunks")
        .select("content, metadata, chunk_index")
        .eq("file_path", file_path)
        .order("chunk_index")
        .execute()
    )
    return result.data


def delete_file_chunks(file_path: str) -> None:
    """Delete all chunks for a file path."""
    client = get_client()
    client.rpc("delete_file_chunks", {"target_file_path": file_path}).execute()


def upsert_chunks(chunks: list[dict]) -> None:
    """Upsert chunks into vault_chunks table."""
    client = get_client()
    client.table("vault_chunks").upsert(
        chunks, on_conflict="file_path,chunk_index"
    ).execute()
