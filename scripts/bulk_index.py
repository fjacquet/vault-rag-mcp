#!/usr/bin/env python3
"""Bulk indexation script for the Second Brain vault.

Indexes all markdown files via Google Gemini gemini-embedding-001 (native 3072d)
and upserts into Qdrant vault_chunks collection.

Usage:
    uv run python scripts/bulk_index.py /path/to/vault [--force]

Options:
    --force     Re-index all files, ignoring file_hash cache
"""

import hashlib
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml
from dotenv import load_dotenv
from tqdm import tqdm

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vault_rag_mcp.embeddings import get_embeddings_batch
from vault_rag_mcp.qdrant_store import (
    delete_file_chunks,
    ensure_collection,
    get_existing_hashes,
    upsert_chunks,
)

load_dotenv()

# Directories and files to skip
SKIP_DIRS = {".obsidian", "templates", ".git", ".trash", ".smart-env", "node_modules"}
MAX_FILE_SIZE = 500 * 1024  # 500 KB
BATCH_SIZE = 50  # Chunks per embedding API call (small batches, parallelized)
WORKERS = 4  # Concurrent embedding requests (4 × 50 = 200 chunks in flight)
MAX_CHUNK_CHARS = (
    2000  # Conservative: ~1500 tokens, safe for Gemini 2048 token/text limit
)
MAX_RETRIES = 5  # Max retries per batch on rate limit errors


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

    body = content[match.end() :]
    return metadata, body


def split_long_chunk(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split a chunk that exceeds max_chars into smaller pieces.

    Splits on paragraph boundaries first, then hard-splits if needed.
    """
    if len(text) <= max_chars:
        return [text]

    result = []
    # Split by double newline (paragraphs)
    paragraphs = re.split(r"\n\n+", text)
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars:
            if current.strip():
                result.append(current.strip())
            # If a single paragraph is too long, hard-split it
            if len(para) > max_chars:
                for j in range(0, len(para), max_chars):
                    piece = para[j : j + max_chars].strip()
                    if piece:
                        result.append(piece)
                current = ""
            else:
                current = para
        else:
            current = current + "\n\n" + para if current else para

    if current.strip():
        result.append(current.strip())

    return result if result else [text[:max_chars]]


def chunk_by_h2(body: str) -> list[str]:
    """Split body text into chunks by H2 headers.

    If the file is short (< 100 chars) or has no H2 headers,
    return the whole body as a single chunk.
    Chunks exceeding MAX_CHUNK_CHARS are split further.
    """
    if len(body.strip()) < 100:
        return []

    sections = re.split(r"(?=^## )", body, flags=re.MULTILINE)
    chunks = [s.strip() for s in sections if s.strip()]

    if not chunks:
        return [body.strip()] if body.strip() else []

    # Split any oversized chunks
    final_chunks = []
    for chunk in chunks:
        final_chunks.extend(split_long_chunk(chunk))

    return final_chunks


def get_para_folder(rel_path: str) -> str:
    """Extract PARA folder from relative path."""
    parts = rel_path.split("/")
    if parts and parts[0] in (
        "0_Inbox",
        "1_Projects",
        "2_Areas",
        "3_Resources",
        "4_Archives",
    ):
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


def fetch_existing_hashes(force: bool) -> dict[str, str]:
    """Fetch existing file_hash values from Qdrant for change detection."""
    if force:
        return {}
    return get_existing_hashes()


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
    chunks_text = chunk_by_h2(body)

    if not chunks_text:
        return None

    para_folder = get_para_folder(rel_path)
    note_type = metadata.get("type", "unknown")
    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    chunks = []
    for i, chunk_text in enumerate(chunks_text):
        chunks.append(
            {
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
            }
        )

    return chunks


def embed_single_chunk(chunk: dict) -> bool:
    """Embed a single chunk individually. Returns True on success."""
    try:
        embeddings = get_embeddings_batch(
            [chunk["content"]], task_type="RETRIEVAL_DOCUMENT"
        )
        chunk["embedding"] = embeddings[0]
        return True
    except Exception:
        return False


def embed_batch_with_retry(batch: list[dict], batch_idx: int) -> tuple[list[dict], int]:
    """Embed a single batch with retry on rate limit. Returns (embedded_chunks, skipped_count)."""
    texts = [c["content"] for c in batch]
    skipped = 0

    for attempt in range(MAX_RETRIES):
        try:
            embeddings = get_embeddings_batch(texts, task_type="RETRIEVAL_DOCUMENT")
            for chunk, emb in zip(batch, embeddings, strict=False):
                chunk["embedding"] = emb
            break
        except Exception as e:
            err_str = str(e).lower()
            if (
                "429" in err_str
                or "rate" in err_str
                or "quota" in err_str
                or "resource" in err_str
            ):
                wait = 2**attempt * 5  # 5s, 10s, 20s, 40s, 80s
                tqdm.write(f"Rate limited (batch {batch_idx}), retry in {wait}s...")
                time.sleep(wait)
            elif attempt < MAX_RETRIES - 1:
                time.sleep(2)
            else:
                # Final attempt failed — retry each chunk individually
                for chunk in batch:
                    if not embed_single_chunk(chunk):
                        skipped += 1
                        tqdm.write(
                            f"Skipped: {chunk['file_path']} chunk {chunk['chunk_index']} ({len(chunk['content'])} chars)"
                        )

    embedded = [c for c in batch if "embedding" in c]
    return embedded, skipped


def embed_and_upsert(all_chunks: list[dict]) -> tuple[int, int]:
    """Embed chunks in parallel batches and upsert to Qdrant. Returns (upserted, skipped)."""
    total = 0
    skipped = 0

    # Split into batches
    batches = []
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batches.append((i // BATCH_SIZE, all_chunks[i : i + BATCH_SIZE]))

    pbar = tqdm(total=len(batches), desc=f"Embedding + upserting ({WORKERS} workers)")

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        # Submit all batches to the thread pool
        futures = {
            executor.submit(embed_batch_with_retry, batch, idx): idx
            for idx, batch in batches
        }

        for future in as_completed(futures):
            embedded, batch_skipped = future.result()
            skipped += batch_skipped

            if embedded:
                try:
                    upsert_chunks(embedded)
                    total += len(embedded)
                except Exception as e:
                    skipped += len(embedded)
                    tqdm.write(f"Upsert error (batch {futures[future]}): {e}")

            pbar.update(1)

    pbar.close()
    return total, skipped


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

    # Ensure Qdrant collection exists with correct config
    ensure_collection()

    # Fetch existing hashes for incremental indexing
    existing_hashes = fetch_existing_hashes(force)
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

    print(
        f"\nParsed: {len(md_files) - skipped - errors} files → {len(all_chunks)} chunks"
    )
    print(f"Skipped (unchanged): {skipped}")
    print(f"Errors: {errors}")

    if not all_chunks:
        print("Nothing to index.")
        return

    # Embed and upsert
    print(
        f"\nEmbedding {len(all_chunks)} chunks via Google Gemini ({WORKERS} workers × batch {BATCH_SIZE})..."
    )
    upserted, skipped = embed_and_upsert(all_chunks)
    print(f"\nDone! Upserted {upserted} chunks to Qdrant.")
    if skipped:
        print(f"Skipped chunks (too long for context): {skipped}")


if __name__ == "__main__":
    main()
