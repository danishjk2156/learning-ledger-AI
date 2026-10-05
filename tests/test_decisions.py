"""Unit tests for the DecisionGate module."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.decisions import DecisionGate


class TestDecisionGate(unittest.TestCase):
    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "fake_test_key"})
    @patch("src.decisions.TypeSafeClient")
    def test_claim_support(self, mock_typesafe):
        mock_client = MagicMock()
        mock_typesafe.return_value = mock_client

        # Mock result.nouls["supported"].noul
        mock_result = SimpleNamespace(
            nouls={"supported": SimpleNamespace(noul=0.88)}
        )
        mock_client.system_one.return_value = mock_result

        gate = DecisionGate()
        score = gate.claim_support("Test claim", "Test quote")
        self.assertEqual(score, 0.88)
        self.assertTrue(mock_client.system_one.called)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "fake_test_key"})
    @patch("src.decisions.TypeSafeClient")
    def test_relevance(self, mock_typesafe):
        mock_client = MagicMock()
        mock_typesafe.return_value = mock_client

        mock_result = SimpleNamespace(
            nouls={"relevant": SimpleNamespace(noul=0.75)}
        )
        mock_client.system_one.return_value = mock_result

        gate = DecisionGate()
        self.assertTrue(gate.relevance("What is LoRA?", "LoRA is low rank adaptation."))

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_raises(self):
        # When OPENROUTER_API_KEY is not set, initializing DecisionGate should raise RuntimeError
        with self.assertRaises(RuntimeError):
            DecisionGate()


if __name__ == "__main__":
    unittest.main()
