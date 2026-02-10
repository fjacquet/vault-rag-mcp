"""Ollama embedding client for local query-time embedding."""

import os

import ollama

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "nomic-embed-text")


def get_embedding(text: str) -> list[float]:
    """Get 768-dim embedding from local Ollama nomic-embed-text."""
    response = ollama.embed(model=OLLAMA_MODEL, input=text)
    return response["embeddings"][0]


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Get embeddings for multiple texts in one call."""
    response = ollama.embed(model=OLLAMA_MODEL, input=texts)
    return response["embeddings"]
