"""OpenRouter embedding client using OpenAI-compatible API."""

import os

import openai

_client = None


def _get_client() -> openai.OpenAI:
    """Lazy-init OpenAI client (allows dotenv to load first)."""
    global _client
    if _client is None:
        _client = openai.OpenAI(
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    return _client


def _get_model() -> str:
    return os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")


def _get_dimensions() -> int:
    return int(os.getenv("EMBEDDING_DIMENSIONS", "768"))


def get_embedding(text: str) -> list[float]:
    """Get embedding from OpenRouter (text-embedding-3-small, 768d by default)."""
    response = _get_client().embeddings.create(
        model=_get_model(), input=text, dimensions=_get_dimensions()
    )
    return response.data[0].embedding


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Get embeddings for multiple texts in one API call."""
    response = _get_client().embeddings.create(
        model=_get_model(), input=texts, dimensions=_get_dimensions()
    )
    return [item.embedding for item in response.data]
