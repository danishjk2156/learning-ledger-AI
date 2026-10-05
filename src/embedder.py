"""
Gemini Embedder — wraps Google Gemini embedding-001 for text embeddings.

Provides both a standalone embedder and a ChromaDB-compatible embedding function.
"""

import os
from google import genai


from typing import Union


class GeminiEmbedder:
    """Generate text embeddings using Gemini embedding models."""

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY not set. Get one at https://aistudio.google.com"
            )
        self.client = genai.Client(api_key=api_key)
        self.model = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (each a list of floats).
        """
        if not texts:
            return []

        try:
            response = self.client.models.embed_content(
                model=self.model,
                contents=texts,
            )
            return [e.values for e in response.embeddings]
        except Exception as e:
            # Fallback to text-embedding-004 if gemini-embedding-001 is unavailable
            if "gemini-embedding-001" in self.model:
                try:
                    fallback_model = "text-embedding-004"
                    response = self.client.models.embed_content(
                        model=fallback_model,
                        contents=texts,
                    )
                    self.model = fallback_model
                    return [e.values for e in response.embeddings]
                except Exception:
                    pass
            raise e

    def embed_single(self, text: str) -> list[float]:
        """Embed a single text string."""
        result = self.embed([text])
        return result[0] if result else []


class GeminiEmbeddingFunction:
    """
    ChromaDB-compatible embedding function using Gemini.

    ChromaDB expects an object with .name(), __call__(input), and .embed_query(input).
    """

    def __init__(self):
        self._embedder = GeminiEmbedder()

    @staticmethod
    def name() -> str:
        return "gemini_embedding"

    def __call__(self, input: Union[str, list[str]]) -> list[list[float]]:
        """Generate embeddings for ChromaDB."""
        if isinstance(input, str):
            input = [input]
        # Batch in groups of 100 to respect rate limits
        all_embeddings = []
        batch_size = 100
        for i in range(0, len(input), batch_size):
            batch = input[i : i + batch_size]
            embeddings = self._embedder.embed(batch)
            all_embeddings.extend(embeddings)
        return all_embeddings

    def embed_query(self, input: Union[str, list[str]]) -> list[list[float]]:
        """Embed a search query for ChromaDB."""
        return self(input)
