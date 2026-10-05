"""Unit tests for the Claim Ledger module."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from src import ledger


class TestLedger(unittest.TestCase):
    def setUp(self):
        # Use a temporary directory for test database
        self.test_dir = tempfile.TemporaryDirectory()
        self.orig_db = ledger.DB
        ledger.DB = os.path.join(self.test_dir.name, "test_ledger.db")
        ledger.init_ledger()

    def tearDown(self):
        ledger.DB = self.orig_db
        self.test_dir.cleanup()

    def test_init_ledger_creates_table(self):
        conn = ledger.init_ledger()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='claims'")
        table = cursor.fetchone()
        self.assertIsNotNone(table)
        self.assertEqual(table[0], "claims")
        conn.close()

    def test_record_claim_supported(self):
        mock_jev = MagicMock()
        mock_jev.claim_support.return_value = 0.95
        mock_llm = MagicMock()

        claim = "LoRA reduces trainable parameters by up to 10,000x."
        source = {
            "doi": "10.48550/arXiv.2106.09685",
            "title": "LoRA: Low-Rank Adaptation of Large Language Models",
            "quote": "LoRA can reduce the number of trainable parameters by 10,000 times.",
            "page": 1,
            "depends_on": []
        }

        entry = ledger.record_claim(claim, source, mock_jev, mock_llm)
        self.assertEqual(entry["claim"], claim)
        self.assertEqual(entry["status"], "active")
        self.assertEqual(entry["confidence"], 0.95)
        self.assertEqual(len(entry["claim_id"]), 12)

        # Verify retrieved from db
        stored = ledger.get_claim(entry["claim_id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["claim"], claim)
        self.assertEqual(stored["doi"], source["doi"])

    def test_record_claim_low_confidence_marked_suspect(self):
        mock_jev = MagicMock()
        mock_jev.claim_support.return_value = 0.25
        mock_llm = MagicMock()

        claim = "Quantum computers have rendered RSA obsolete in 2024."
        source = {
            "doi": "10.1234/test",
            "title": "Quantum Limits",
            "quote": "Current quantum systems remain decades away from breaking RSA.",
            "page": 5,
        }

        entry = ledger.record_claim(claim, source, mock_jev, mock_llm)
        self.assertEqual(entry["status"], "suspect")
        self.assertEqual(entry["confidence"], 0.25)

    def test_update_claim_status(self):
        mock_jev = MagicMock()
        mock_jev.claim_support.return_value = 0.9
        mock_llm = MagicMock()

        entry = ledger.record_claim(
            "Test Claim",
            {"doi": "10.1000/1", "quote": "Test Quote"},
            mock_jev,
            mock_llm
        )

        ledger.update_claim_status(entry["claim_id"], "retracted", note="Paper retracted by publisher")
        updated = ledger.get_claim(entry["claim_id"])
        self.assertEqual(updated["status"], "retracted")
        self.assertEqual(updated["note"], "Paper retracted by publisher")

    def test_get_all_claims_filtering(self):
        mock_jev = MagicMock()
        mock_llm = MagicMock()

        mock_jev.claim_support.return_value = 0.9
        ledger.record_claim("Active Claim", {"doi": "1", "quote": "Q1"}, mock_jev, mock_llm)

        mock_jev.claim_support.return_value = 0.2
        ledger.record_claim("Suspect Claim", {"doi": "2", "quote": "Q2"}, mock_jev, mock_llm)

        all_claims = ledger.get_all_claims()
        self.assertEqual(len(all_claims), 2)

        active = ledger.get_all_claims(status="active")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["status"], "active")

        suspect = ledger.get_all_claims(status="suspect")
        self.assertEqual(len(suspect), 1)
        self.assertEqual(suspect[0]["status"], "suspect")


if __name__ == "__main__":
    unittest.main()
