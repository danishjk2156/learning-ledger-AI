"""
Retriever — ChromaDB vector store with Gemini embeddings.

Stores paper chunks as embeddings and retrieves the most relevant ones
for a given question via similarity search.
"""

import chromadb
from .embedder import GeminiEmbeddingFunction

CHROMA_PATH = ".ledger/chroma"


class Retriever:
    """Vector store for paper chunks backed by ChromaDB + Gemini embeddings."""

    def __init__(self, chroma_path: str = CHROMA_PATH):
        self.client = chromadb.PersistentClient(path=chroma_path)
        self.embed_fn = GeminiEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name="papers",
            embedding_function=self.embed_fn,
        )

    def add(
        self,
        chunks: list[str],
        metadatas: list[dict],
        ids: list[str],
    ):
        """
        Add text chunks with metadata to the vector store.

        Args:
            chunks: List of text strings.
            metadatas: List of metadata dicts (doi, source, page, etc.).
            ids: List of unique IDs for each chunk.
        """
        if not chunks:
            return
        self.collection.add(
            documents=chunks,
            metadatas=metadatas,
            ids=ids,
        )

    def query(
        self, question: str, n_results: int = 5
    ) -> tuple[list[str], list[dict]]:
        """
        Query for the most relevant chunks.

        Args:
            question: The search query.
            n_results: Number of results to return.

        Returns:
            Tuple of (documents, metadatas).
        """
        results = self.collection.query(
            query_texts=[question],
            n_results=min(n_results, self.collection.count() or 1),
        )
        docs = results["documents"][0] if results["documents"] else []
        metas = results["metadatas"][0] if results["metadatas"] else []
        return docs, metas

    def count(self) -> int:
        """Return the total number of chunks stored."""
        return self.collection.count()

    def delete_by_doi(self, doi: str):
        """Delete all chunks for a specific DOI."""
        if not doi:
            return
        # ChromaDB supports filtering by metadata
        results = self.collection.get(where={"doi": doi})
        if results["ids"]:
            self.collection.delete(ids=results["ids"])

    def list_sources(self) -> list[str]:
        """List all unique source titles in the collection."""
        results = self.collection.get(include=["metadatas"])
        sources = set()
        for meta in results.get("metadatas", []):
            if meta and meta.get("source"):
                sources.add(meta["source"])
        return sorted(sources)

    def reset_collection(self):
        """Delete and recreate the papers collection to purge contaminated chunks."""
        try:
            self.client.delete_collection("papers")
        except Exception as e:
            print(f"[Retriever] Notice deleting collection: {e}")
        self.collection = self.client.get_or_create_collection(
            name="papers",
            embedding_function=self.embed_fn,
        )
