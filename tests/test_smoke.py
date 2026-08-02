"""Smoke tests for the vault-rag MCP server.

These verify the package imports cleanly and the MCP server exposes its three
tools without requiring any network credentials (clients are lazy-initialized).
"""

from importlib.metadata import version

from vault_rag_mcp import server


def test_server_module_imports():
    """The server module imports without instantiating any network client."""
    assert server.mcp is not None
    assert server.mcp.name == "vault-rag"


def test_server_reports_package_version():
    """The server's init metadata exposes the installed package version."""
    assert server.mcp.version == version("vault-rag-mcp")


def test_format_result_truncates_long_content():
    """_format_result renders the metadata header and truncates long content."""
    out = server._format_result(
        {
            "similarity": 0.42,
            "file_path": "3_Resources/definitions/p/note.md",
            "para_folder": "3_Resources",
            "note_type": "glossary",
            "content": "x" * 600,
        }
    )
    assert "[0.420]" in out
    assert "3_Resources/definitions/p/note.md" in out
    assert "(3_Resources/glossary)" in out
    # 600 chars of content are truncated to 500 + an ellipsis marker.
    assert out.count("x") == 500
    assert "..." in out


def test_format_result_handles_missing_fields():
    """_format_result tolerates an empty/partial result dict."""
    out = server._format_result({})
    assert "[0.000]" in out
    assert "unknown" in out


def test_expected_tools_are_defined():
    """The three documented tools exist as callables on the server module."""
    for name in ("search_vault", "search_glossary", "get_note"):
        assert callable(getattr(server, name))
