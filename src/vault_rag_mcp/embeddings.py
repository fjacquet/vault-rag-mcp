"""Google Gemini embedding client using google-genai SDK."""

import os

from google import genai
from google.genai.types import EmbedContentConfig

_client = None


def _get_client() -> genai.Client:
    """Lazy-init Google GenAI client (allows dotenv to load first)."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return _client


def _get_model() -> str:
    return os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")


def get_embedding(text: str, task_type: str = "SEMANTIC_SIMILARITY") -> list[float]:
    """Get embedding from Google Gemini (native 3072d, already L2-normalized)."""
    response = _get_client().models.embed_content(
        model=_get_model(),
        contents=text,
        config=EmbedContentConfig(task_type=task_type),
    )
    return response.embeddings[0].values


def get_embeddings_batch(
    texts: list[str], task_type: str = "SEMANTIC_SIMILARITY"
) -> list[list[float]]:
    """Get embeddings for multiple texts in one API call (max 250 per call)."""
    response = _get_client().models.embed_content(
        model=_get_model(),
        contents=texts,
        config=EmbedContentConfig(task_type=task_type),
    )
    return [emb.values for emb in response.embeddings]
