# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`vault-rag-mcp` is an **MCP server** (FastMCP) that provides semantic search over an
Obsidian "Second Brain" vault. Notes are embedded with **Google Gemini embeddings** and
indexed in a self-hosted **Qdrant** vector store; the server exposes search tools to MCP
clients (e.g. Claude). Python, managed with **uv**.

## Commands

Everything CI runs is a Makefile target, so it reproduces locally (`uv` resolves deps).

- `make ci` — the full gate: `lint test build`.
- `make lint` — `uv run ruff check .`; `make format` — `ruff format`.
- `make test` — `uv run pytest --cov` (coverage to `coverage.xml` + terminal).
- Run a single test: `uv run pytest tests/<file>::<test> -q`.
- `make build` — `uv build` (sdist + wheel).
- `make docs` — `uv run mkdocs build --strict` (MkDocs Material site).
- `make security` — advisory scan (semgrep); non-blocking. CodeQL + osv-scan are the blocking gates.
- `make vuln` / `make sbom` — vulnerability scan / CycloneDX SBOM.
- Run the server: `uv run vault-rag-mcp` (entrypoint `vault_rag_mcp.server:main`).

## Architecture

- `src/vault_rag_mcp/server.py` — FastMCP server; wires the MCP tools and the `main()` entrypoint.
- `src/vault_rag_mcp/embeddings.py` — Google Gemini embedding generation.
- `src/vault_rag_mcp/qdrant_store.py` — Qdrant client + collection management and vector upsert/query.
- `scripts/` — indexing/maintenance helpers; `n8n-workflows/` — automation workflows; `tests/` — pytest suite.

## CI/CD

Thin callers to the central reusable workflows in `fjacquet/ci@v1`:
`python-ci.yml` (lint/test/build), `python-security.yml` (CodeQL/osv/sbom), `docs-publish.yml` (MkDocs → GitHub Pages).
