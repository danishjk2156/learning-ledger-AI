"""
Granite Question Classifier — Local query router for Learning Ledger.

Classifies incoming queries into:
  - "conversational": greetings, pleasantries, questions about the assistant, small talk.
  - "paper_query": scientific questions, methodologies, claims, benchmarks, paper lookups.

Supports:
1. cnmoro/granite-question-classifier via Hugging Face transformers/PyTorch (if installed).
2. IBM Granite via local Ollama runtime (e.g., granite3-dense:2b).
3. Ultra-fast, zero-overhead heuristic classifier fallback.
"""

import os
import requests
from .utils import safe_parse_json

CLASSIFICATION_PROMPT = """You are an accurate binary query router for an academic research paper assistant.
Classify the user's input into one of two labels:
- "conversational": greetings, small talk, pleasantries, questions about who you are, what you can do, or general chatter (e.g., "hi", "how are you", "who are you", "what can you do", "thanks", "test").
- "paper_query": questions seeking scientific facts, paper methodologies, benchmarks, datasets, author claims, findings, or concepts from research literature.

User input: "{query}"

Output ONLY a JSON object with a single key "label" whose value is either "conversational" or "paper_query".
JSON:"""


class GraniteQuestionClassifier:
    """
    Local question classifier for query routing.
    """

    def __init__(
        self,
        ollama_url: str = None,
        model: str = None,
    ):
        base_url = ollama_url or os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.endpoint = f"{base_url.rstrip('/')}/api/generate"
        self.model = model or os.getenv("GRANITE_MODEL", "granite3-dense:2b")
        self._hf_model = None
        self._hf_tokenizer = None
        self._tried_hf = False
        self._ollama_available = None

    def _init_hf(self):
        """Try initializing Hugging Face cnmoro/granite-question-classifier if available."""
        if self._tried_hf:
            return
        self._tried_hf = True
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            model_id = "cnmoro/granite-question-classifier"
            self._hf_tokenizer = AutoTokenizer.from_pretrained(model_id)
            self._hf_model = AutoModelForSequenceClassification.from_pretrained(model_id)
            print("[Classifier] cnmoro/granite-question-classifier loaded successfully.")
        except Exception:
            # Fall back cleanly if torch / transformers not installed or offline
            self._hf_model = None
            self._hf_tokenizer = None

    def classify(self, query: str) -> str:
        """
        Classify a query as 'conversational' or 'paper_query'.
        """
        query_clean = query.strip()
        if not query_clean:
            return "conversational"

        # 1. Try Hugging Face Granite Question Classifier if available
        self._init_hf()
        if self._hf_model and self._hf_tokenizer:
            try:
                import torch
                inputs = self._hf_tokenizer.encode_plus(
                    query_clean, return_tensors="pt", truncation=True, max_length=512
                )
                with torch.no_grad():
                    logits = self._hf_model(**inputs).logits.squeeze(-1)
                # Class 0 = Generic (conversational), Class 1 = Directed (paper_query)
                pred = (logits > 0).float().item()
                return "paper_query" if pred == 1.0 else "conversational"
            except Exception:
                pass

        # 2. Try local Granite model via Ollama
        try:
            resp = requests.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "prompt": CLASSIFICATION_PROMPT.format(query=query_clean),
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.0},
                },
                timeout=1.2,
            )
            if resp.status_code == 200:
                result_json = resp.json().get("response", "{}")
                data = safe_parse_json(result_json, fallback={})
                label = data.get("label", "").lower().strip()
                if label in ("conversational", "paper_query"):
                    if not self._ollama_available:
                        print(f"[Classifier] IBM Granite ({self.model}) active locally.")
                        self._ollama_available = True
                    return label
        except Exception:
            pass

        # 3. High-accuracy rule fallback
        return self._rule_fallback(query_clean)

    def _rule_fallback(self, query: str) -> str:
        """Accurate rule-based classification fallback."""
        clean = query.strip().lower()
        stripped = "".join(c for c in clean if c.isalnum() or c.isspace()).strip()

        # Direct conversational markers
        greetings = {
            "hi", "hello", "hey", "hola", "howdy", "sup", "yo",
            "how", "what", "who", "why", "help", "test",
            "how are you", "how are you doing", "how are u", "hows it going",
            "good morning", "good afternoon", "good evening", "good day",
            "who are you", "what are you", "what can you do", "what do you do",
            "tell me about yourself", "how does this work",
            "thanks", "thank you", "thx", "bye", "goodbye", "see ya",
            "ok", "okay", "cool", "nice", "great", "awesome", "yes", "no",
        }

        if stripped in greetings:
            return "conversational"

        greeting_starters = ("hi ", "hello ", "hey ", "good morning ", "good evening ")
        if any(clean.startswith(p) for p in greeting_starters) and len(clean.split()) <= 3:
            return "conversational"

        # Explicit paper/research markers always trigger paper_query
        paper_markers = [
            "paper", "papers", "study", "research", "author", "authors",
            "deepfake", "method", "methodology", "model", "algorithm",
            "experiment", "dataset", "accuracy", "result", "results",
            "citation", "cite", "claim", "claims", "finding", "findings",
            "teach me", "explain the", "summarize", "summary", "overview",
            "ingested", "library", "what does", "how does", "according to",
        ]
        if any(m in clean for m in paper_markers):
            return "paper_query"

        # Questions longer than 4 words with substantive content default to paper query
        if len(clean.split()) > 3:
            return "paper_query"

        return "conversational"


_classifier_instance = None


def get_classifier() -> GraniteQuestionClassifier:
    """Return the singleton instance of GraniteQuestionClassifier."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = GraniteQuestionClassifier()
    return _classifier_instance
