#!/usr/bin/env python3
"""Bulk indexation script for the Second Brain vault.

Indexes all markdown files via local Ollama nomic-embed-text (768d)
and upserts into Supabase pgvector vault_chunks table.

Usage:
    uv run python scripts/bulk_index.py /path/to/vault [--force]

Options:
    --force     Re-index all files, ignoring file_hash cache
"""

import hashlib
import re
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from tqdm import tqdm

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vault_rag_mcp.embeddings import get_embedding, get_embeddings_batch
from vault_rag_mcp.supabase_client import delete_file_chunks, get_client, upsert_chunks

load_dotenv()

# Directories and files to skip
SKIP_DIRS = {".obsidian", "templates", ".git", ".trash", ".smart-env", "node_modules"}
MAX_FILE_SIZE = 500 * 1024  # 500 KB
BATCH_SIZE = 20  # Chunks per embedding batch


def file_hash(content: str) -> str:
    """SHA256 hash of file content."""
    return hashlib.sha256(content.encode()).hexdigest()


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content.

    Returns (metadata_dict, body_text).
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", content, re.DOTALL)
    if not match:
        return {}, content

    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        metadata = {}

    body = content[match.end():]
    return metadata, body


def chunk_by_h2(body: str, file_path: str) -> list[str]:
    """Split body text into chunks by H2 headers.

    If the file is short (< 1000 chars) or has no H2 headers,
    return the whole body as a single chunk.
    """
    if len(body.strip()) < 100:
        return []

    sections = re.split(r"(?=^## )", body, flags=re.MULTILINE)
    chunks = [s.strip() for s in sections if s.strip()]

    if not chunks:
        return [body.strip()] if body.strip() else []

    return chunks


def get_para_folder(rel_path: str) -> str:
    """Extract PARA folder from relative path."""
    parts = rel_path.split("/")
    if parts and parts[0] in ("0_Inbox", "1_Projects", "2_Areas", "3_Resources", "4_Archives"):
        return parts[0]
    return "other"


def should_skip(path: Path, vault_root: Path) -> bool:
    """Check if a file should be skipped."""
    rel_parts = path.relative_to(vault_root).parts
    # Skip if any parent directory is in SKIP_DIRS
    if any(part in SKIP_DIRS for part in rel_parts):
        return True
    # Skip non-markdown files
    if path.suffix != ".md":
        return True
    # Skip large files
    if path.stat().st_size > MAX_FILE_SIZE:
        return True
    return False


def get_existing_hashes(client) -> dict[str, str]:
    """Fetch existing file_hash values from Supabase for change detection."""
    result = (
        client.table("vault_chunks")
        .select("file_path, file_hash")
        .eq("chunk_index", 0)
        .execute()
    )
    return {r["file_path"]: r["file_hash"] for r in result.data if r.get("file_hash")}


def index_file(
    path: Path,
    vault_root: Path,
    existing_hashes: dict[str, str],
    force: bool = False,
) -> list[dict] | None:
    """Parse and chunk a single file. Returns chunks ready for embedding, or None if skipped."""
    rel_path = str(path.relative_to(vault_root))
    content = path.read_text(encoding="utf-8", errors="replace")
    content_hash = file_hash(content)

    # Skip if unchanged (unless --force)
    if not force and existing_hashes.get(rel_path) == content_hash:
        return None

    metadata, body = parse_frontmatter(content)
    chunks_text = chunk_by_h2(body, rel_path)

    if not chunks_text:
        return None

    para_folder = get_para_folder(rel_path)
    note_type = metadata.get("type", "unknown")
    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    chunks = []
    for i, chunk_text in enumerate(chunks_text):
        chunks.append({
            "content": chunk_text,
            "file_path": rel_path,
            "chunk_index": i,
            "para_folder": para_folder,
            "note_type": note_type if isinstance(note_type, str) else "unknown",
            "file_hash": content_hash if i == 0 else None,
            "metadata": {
                "tags": tags,
                "type": note_type,
                "para_folder": para_folder,
            },
        })

    return chunks


def embed_and_upsert(all_chunks: list[dict]) -> int:
    """Embed chunks in batches and upsert to Supabase. Returns count of upserted chunks."""
    total = 0

    for i in tqdm(range(0, len(all_chunks), BATCH_SIZE), desc="Embedding + upserting"):
        batch = all_chunks[i : i + BATCH_SIZE]
        texts = [c["content"] for c in batch]

        embeddings = get_embeddings_batch(texts)

        for chunk, emb in zip(batch, embeddings):
            chunk["embedding"] = emb

        upsert_chunks(batch)
        total += len(batch)

    return total


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/bulk_index.py /path/to/vault [--force]")
        sys.exit(1)

    vault_root = Path(sys.argv[1]).resolve()
    force = "--force" in sys.argv

    if not vault_root.is_dir():
        print(f"Error: {vault_root} is not a directory")
        sys.exit(1)

    print(f"Vault: {vault_root}")
    print(f"Force re-index: {force}")

    # Collect all markdown files
    md_files = [p for p in vault_root.rglob("*.md") if not should_skip(p, vault_root)]
    print(f"Found {len(md_files)} markdown files to process")

    # Fetch existing hashes for incremental indexing
    client = get_client()
    existing_hashes = {} if force else get_existing_hashes(client)
    print(f"Existing indexed files: {len(existing_hashes)}")

    # Parse and chunk all files
    all_chunks: list[dict] = []
    skipped = 0
    errors = 0

    for path in tqdm(md_files, desc="Parsing files"):
        try:
            chunks = index_file(path, vault_root, existing_hashes, force)
            if chunks is None:
                skipped += 1
                continue
            # Delete old chunks for this file before re-indexing
            rel_path = str(path.relative_to(vault_root))
            if rel_path in existing_hashes:
                delete_file_chunks(rel_path)
            all_chunks.extend(chunks)
        except Exception as e:
            errors += 1
            tqdm.write(f"Error processing {path}: {e}")

    print(f"\nParsed: {len(md_files) - skipped - errors} files → {len(all_chunks)} chunks")
    print(f"Skipped (unchanged): {skipped}")
    print(f"Errors: {errors}")

    if not all_chunks:
        print("Nothing to index.")
        return

    # Embed and upsert
    print(f"\nEmbedding {len(all_chunks)} chunks via Ollama (batch size {BATCH_SIZE})...")
    upserted = embed_and_upsert(all_chunks)
    print(f"\nDone! Upserted {upserted} chunks to Supabase.")


if __name__ == "__main__":
    main()
