"""Unit tests for the Integrity Layer (Retraction & Decay)."""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.integrity import decay, retraction


class TestRetraction(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.orig_db = retraction.DB_PATH
        retraction.DB_PATH = os.path.join(self.test_dir.name, "test_retraction.db")
        # Clear lru_cache between tests
        retraction.check_retraction.cache_clear()

    def tearDown(self):
        retraction.DB_PATH = self.orig_db
        retraction.check_retraction.cache_clear()
        self.test_dir.cleanup()

    def test_local_retraction_lookup(self):
        # Setup local db directly
        conn = sqlite3.connect(retraction.DB_PATH)
        conn.execute("""
            CREATE TABLE retractions (
                doi TEXT PRIMARY KEY,
                title TEXT,
                reason TEXT,
                date TEXT
            )
        """)
        conn.execute(
            "INSERT INTO retractions VALUES (?, ?, ?, ?)",
            ("10.1000/retracted-paper", "Faulty Paper", "Data falsification", "2023-01-15")
        )
        conn.commit()
        conn.close()

        result = retraction.check_retraction("10.1000/retracted-paper")
        self.assertEqual(result["status"], "retracted")
        self.assertEqual(result["reason"], "Data falsification")
        self.assertEqual(result["source"], "retraction_watch_local")

    @patch("requests.get")
    def test_crossref_api_retraction(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "update-to": [
                    {
                        "type": "retraction",
                        "label": "Retraction notice for Study X",
                        "updated": "2024-05-01"
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        result = retraction.check_retraction("10.1000/crossref-retracted")
        self.assertEqual(result["status"], "retracted")
        self.assertEqual(result["source"], "crossref_api")

    @patch("requests.get")
    def test_crossref_api_ok(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "update-to": []
            }
        }
        mock_get.return_value = mock_response

        result = retraction.check_retraction("10.1000/valid-paper")
        self.assertEqual(result["status"], "ok")


class TestConfidenceDecay(unittest.TestCase):
    def test_time_based_decay_calculation(self):
        mock_jev = MagicMock()
        cd = decay.ConfidenceDecay(mock_jev)

        # 1 year old ML paper vs 10 year old math paper
        res_recent = cd.score({
            "publication_date": "2025-01-01",
            "field": "machine_learning",
            "cited_by_count": 50
        })
        self.assertIn("decay_factor", res_recent)
        self.assertIn("recommendation", res_recent)
        self.assertGreater(res_recent["decay_factor"], 0.0)
        self.assertLessEqual(res_recent["decay_factor"], 1.0)


if __name__ == "__main__":
    unittest.main()
