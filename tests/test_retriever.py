"""Unit tests for Retriever module."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.retriever import Retriever


class DummyEmbeddingFunction:
    """Mock embedding function returning deterministic 4-dim vectors for testing."""
    def __call__(self, input: list[str]) -> list[list[float]]:
        # Return dummy vector for each text
        return [[0.1, 0.2, 0.3, 0.4] for _ in input]


class TestRetriever(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.test_dir.cleanup()

    @patch("src.retriever.GeminiEmbeddingFunction", return_value=DummyEmbeddingFunction())
    def test_add_query_and_count(self, mock_embed_fn):
        retriever = Retriever(chroma_path=self.test_dir.name)
        self.assertEqual(retriever.count(), 0)

        chunks = ["Chunk 1 about LLMs", "Chunk 2 about protein folding"]
        metas = [
            {"source": "paper1.pdf", "doi": "10.1001/p1", "page": 1},
            {"source": "paper2.pdf", "doi": "10.1002/p2", "page": 2},
        ]
        ids = ["c1", "c2"]

        retriever.add(chunks, metas, ids)
        self.assertEqual(retriever.count(), 2)

        docs, returned_metas = retriever.query("LLMs", n_results=1)
        self.assertEqual(len(docs), 1)
        self.assertEqual(len(returned_metas), 1)

    @patch("src.retriever.GeminiEmbeddingFunction", return_value=DummyEmbeddingFunction())
    def test_delete_by_doi(self, mock_embed_fn):
        retriever = Retriever(chroma_path=self.test_dir.name)
        chunks = ["Chunk A", "Chunk B"]
        metas = [
            {"source": "paperA.pdf", "doi": "10.1000/delete-me"},
            {"source": "paperB.pdf", "doi": "10.1000/keep-me"},
        ]
        ids = ["id_a", "id_b"]

        retriever.add(chunks, metas, ids)
        self.assertEqual(retriever.count(), 2)

        retriever.delete_by_doi("10.1000/delete-me")
        self.assertEqual(retriever.count(), 1)
        self.assertEqual(retriever.list_sources(), ["paperB.pdf"])


if __name__ == "__main__":
    unittest.main()
