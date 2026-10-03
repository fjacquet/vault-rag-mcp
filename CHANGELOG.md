# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Standing practice: on each release, move `[Unreleased]` to a dated `[X.Y.Z]`
section rather than letting it accumulate indefinitely.

## [Unreleased]

### Changed

- Refreshed `uv.lock` (2026-10-02 dependency sweep).
- The Security workflow now also runs on a weekly schedule and can be triggered manually.

### Security

- Resolved Dependabot security alerts and bumped `httpx2` to 2.12.0 with a full `uv.lock` refresh.

## [1.0.0] - 2026-08-02

### Changed

- Upgraded the `mcp` SDK to v2.0 and pass an explicit version to `MCPServer`.

## [0.1.0] - 2026-08-01

First tagged release. Before this tag the project:

- Started (2026-02-10) as an MCP server with Ollama embeddings and Supabase pgvector, with a bulk indexation script for the vault.
- Migrated the vector store from Supabase pgvector to Qdrant and the embeddings to Google `gemini-embedding-001` (native 3072d).
- Lowered `MAX_CHUNK_CHARS` to 2000 with a per-chunk retry fallback, and parallelised bulk indexation over 4 workers.
- Adopted the shared `fjacquet/ci@v1` CI (fixing a `maincd` branch-filter typo) and cleared Dependabot alerts via full `uv.lock` upgrades.

[Unreleased]: https://github.com/fjacquet/vault-rag-mcp/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/fjacquet/vault-rag-mcp/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/fjacquet/vault-rag-mcp/releases/tag/v0.1.0
