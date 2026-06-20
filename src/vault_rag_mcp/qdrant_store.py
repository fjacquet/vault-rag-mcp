"""Qdrant client for vault_chunks operations."""

import os
import uuid

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    Range,
    VectorParams,
)

load_dotenv()

COLLECTION = "vault_chunks"
VECTOR_SIZE = 3072
_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

_client: QdrantClient | None = None


def _point_id(file_path: str, chunk_index: int) -> str:
    """Deterministic UUID5 from file_path::chunk_index."""
    return str(uuid.uuid5(_NAMESPACE, f"{file_path}::{chunk_index}"))


def get_client() -> QdrantClient:
    """Get or create Qdrant client singleton."""
    global _client
    if _client is None:
        url = os.environ["QDRANT_URL"]
        if "://" in url and ":443" not in url and url.startswith("https"):
            url = url.rstrip("/") + ":443"
        _client = QdrantClient(
            url=url,
            api_key=os.environ.get("QDRANT_API_KEY"),
            timeout=30,
        )
    return _client


def ensure_collection() -> None:
    """Create collection and payload indexes if they don't exist."""
    client = get_client()
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    for field, schema in [
        ("file_path", PayloadSchemaType.KEYWORD),
        ("para_folder", PayloadSchemaType.KEYWORD),
        ("note_type", PayloadSchemaType.KEYWORD),
        ("chunk_index", PayloadSchemaType.INTEGER),
    ]:
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name=field,
            field_schema=schema,
            wait=True,
        )


def search_vault(
    query_embedding: list[float],
    match_count: int = 10,
    filter_para_folder: str | None = None,
    filter_note_type: str | None = None,
) -> list[dict]:
    """Semantic search via Qdrant."""
    conditions = []
    if filter_para_folder:
        conditions.append(
            FieldCondition(
                key="para_folder", match=MatchValue(value=filter_para_folder)
            )
        )
    if filter_note_type:
        conditions.append(
            FieldCondition(key="note_type", match=MatchValue(value=filter_note_type))
        )

    result = get_client().query_points(
        collection_name=COLLECTION,
        query=query_embedding,
        query_filter=Filter(must=conditions) if conditions else None,
        limit=match_count,
        with_payload=True,
    )
    return [
        {
            "id": str(pt.id),
            "content": pt.payload.get("content", ""),
            "metadata": pt.payload.get("metadata", {}),
            "file_path": pt.payload.get("file_path", ""),
            "para_folder": pt.payload.get("para_folder", ""),
            "note_type": pt.payload.get("note_type", ""),
            "similarity": pt.score,
        }
        for pt in result.points
    ]


def get_note_chunks(file_path: str) -> list[dict]:
    """Get all chunks for a file path, ordered by chunk_index."""
    records, _ = get_client().scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
        ),
        limit=200,
        with_payload=True,
        with_vectors=False,
    )
    chunks = [
        {
            "content": r.payload.get("content", ""),
            "metadata": r.payload.get("metadata", {}),
            "chunk_index": r.payload.get("chunk_index", 0),
        }
        for r in records
    ]
    chunks.sort(key=lambda c: c["chunk_index"])
    return chunks


def delete_file_chunks(file_path: str) -> None:
    """Delete all chunks for a file path."""
    get_client().delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(key="file_path", match=MatchValue(value=file_path))
                ]
            )
        ),
        wait=True,
    )


def upsert_chunks(chunks: list[dict]) -> None:
    """Upsert chunks into Qdrant collection."""
    points = [
        PointStruct(
            id=_point_id(c["file_path"], c["chunk_index"]),
            vector=c["embedding"],
            payload={
                "content": c["content"],
                "file_path": c["file_path"],
                "chunk_index": c["chunk_index"],
                "para_folder": c.get("para_folder", ""),
                "note_type": c.get("note_type", ""),
                "file_hash": c.get("file_hash"),
                "metadata": c.get("metadata", {}),
            },
        )
        for c in chunks
    ]
    get_client().upsert(collection_name=COLLECTION, points=points, wait=True)


def get_existing_hashes() -> dict[str, str]:
    """Fetch existing file_hash values for change detection."""
    client = get_client()
    hashes: dict[str, str] = {}
    offset = None

    while True:
        records, offset = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=Filter(
                must=[FieldCondition(key="chunk_index", range=Range(gte=0, lte=0))]
            ),
            limit=1000,
            offset=offset,
            with_payload=["file_path", "file_hash"],
            with_vectors=False,
        )
        for r in records:
            fp = r.payload.get("file_path")
            fh = r.payload.get("file_hash")
            if fp and fh:
                hashes[fp] = fh
        if offset is None or len(records) == 0:
            break

    return hashes
