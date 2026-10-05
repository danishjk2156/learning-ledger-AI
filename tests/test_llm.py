"""Unit tests for Gemini LLM Client."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.llm import LLMClient


class TestLLMClient(unittest.TestCase):
    @patch.dict(os.environ, {"GOOGLE_API_KEY": "fake_google_key"})
    @patch("src.llm.genai.Client")
    def test_generate(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = SimpleNamespace(
            text="Synthetic answer from Gemini"
        )

        llm = LLMClient()
        response = llm.generate("Hello world", system="You are helpful.")
        self.assertEqual(response, "Synthetic answer from Gemini")
        self.assertTrue(mock_client.models.generate_content.called)

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "fake_google_key"})
    @patch("src.llm.genai.Client")
    def test_chat(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = SimpleNamespace(
            text="Chat reply from Gemini"
        )

        llm = LLMClient()
        messages = [
            {"role": "system", "content": "You are a research assistant."},
            {"role": "user", "content": "What is attention?"},
        ]
        response = llm.chat(messages)
        self.assertEqual(response, "Chat reply from Gemini")
        self.assertTrue(mock_client.models.generate_content.called)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_raises(self):
        with self.assertRaises(RuntimeError):
            LLMClient()


if __name__ == "__main__":
    unittest.main()
