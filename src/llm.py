"""
Gemini LLM Client — wraps Google Gemini 3.8 Flash for chat and generation.

Replaces the original ModelRouter. No local/API fallback — cloud-only via Gemini.
"""

import os
from google import genai
from google.genai import types


class LLMClient:
    """Thin wrapper around Google Gemini for chat and single-shot generation."""

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY not set. Get one at https://aistudio.google.com"
            )
        self.client = genai.Client(api_key=api_key)
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    def _call_with_fallback(self, func, **kwargs):
        """Call generation with automatic fallback to active Gemini models if one fails (503/429/404)."""
        candidates = [
            self.model,
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-2.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.8-flash",
        ]
        unique_candidates = []
        for c in candidates:
            if c and c not in unique_candidates:
                unique_candidates.append(c)

        last_err = None
        for candidate in unique_candidates:
            try:
                kwargs["model"] = candidate
                res = func(**kwargs)
                self.model = candidate
                return res
            except Exception as e:
                print(f"[LLM] Candidate {candidate} error: {e}. Trying fallback...")
                last_err = e
                continue
        raise last_err

    def chat(self, messages: list[dict]) -> str:
        """
        Send a conversation to Gemini and return the assistant's reply.

        Args:
            messages: List of dicts with 'role' ('system'|'user'|'assistant')
                      and 'content' keys.

        Returns:
            The model's response text.
        """
        # Extract system instruction if present
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        system_instruction = "\n".join(system_parts) if system_parts else None

        # Build conversation contents (Gemini uses 'user' and 'model' roles)
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                continue  # handled via system_instruction
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part(text=msg["content"])],
                )
            )

        config = types.GenerateContentConfig()
        if system_instruction:
            config.system_instruction = system_instruction

        response = self._call_with_fallback(
            self.client.models.generate_content,
            contents=contents,
            config=config,
        )
        return response.text

    def generate(self, prompt: str, system: str = None) -> str:
        """
        Single prompt → response (no conversation history).

        Args:
            prompt: The user prompt.
            system: Optional system instruction.

        Returns:
            The model's response text.
        """
        config = types.GenerateContentConfig()
        if system:
            config.system_instruction = system

        response = self._call_with_fallback(
            self.client.models.generate_content,
            contents=prompt,
            config=config,
        )
        return response.text

    def generate_json(self, prompt: str, system: str = None) -> dict:
        """
        Single prompt -> parsed JSON dict with safety fallback.
        Ensures responses are never unhandled raw text or crashed JSON.
        """
        from .utils import safe_parse_json
        res_text = self.generate(prompt, system=system)
        return safe_parse_json(res_text)
