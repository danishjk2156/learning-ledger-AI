"""
Jev Decision Gate — structured decision model for typed AI judgments.

Uses TypeSafe SDK to call Jev 1.13 via OpenRouter. Returns typed results
(probabilities, choices, scores) instead of prose.

Key types:
  - Noul: yes/no probability (0.0–1.0)
  - Choice: pick from options (with probability distribution)
  - Score: rate on a rubric scale
"""

import os
from typesafe_sdk import TypeSafeClient, Noul, Choice, Score


class DecisionGate:
    """
    Structured decision gate using Jev 1.13.

    Instead of asking an LLM "is this relevant?" and parsing prose,
    Jev returns a typed probability that can be used directly in code.
    """

    def __init__(self):
        # TypeSafeClient reads OPENROUTER_API_KEY from environment
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY not set. Get one at https://openrouter.ai/keys"
            )
        self.client = TypeSafeClient(api_key=api_key)

    def relevance(self, question: str, chunk: str) -> bool:
        """
        Is this chunk relevant to the research question?

        Args:
            question: The user's research question.
            chunk: A text chunk from a paper.

        Returns:
            True if the chunk is relevant (Noul > 0.6).
        """
        result = self.client.system_one(
            state={"question": question, "chunk": chunk[:2000]},
            questions={
                "relevant": Noul(
                    instructions="Is this chunk relevant to the research question?"
                )
            },
        )
        return result.nouls["relevant"].noul > 0.6

    def claim_support(self, claim: str, quote: str) -> float:
        """
        Does this quote directly support this claim?

        Args:
            claim: The user's claim in their own words.
            quote: The exact quote from the paper.

        Returns:
            Probability (0.0–1.0) that the quote supports the claim.
        """
        result = self.client.system_one(
            state={"claim": claim, "quote": quote},
            questions={
                "supported": Noul(
                    instructions="Does this quote directly support this claim? "
                    "Consider whether the claim accurately represents "
                    "the quote without overstating or misinterpreting it."
                )
            },
        )
        return result.nouls["supported"].noul

    def route(self, question: str, context_size: int) -> tuple[str, dict]:
        """
        How should this question be handled?

        Args:
            question: The user's question.
            context_size: Number of retrieved chunks available.

        Returns:
            Tuple of (chosen_action, probability_distribution).
        """
        result = self.client.system_one(
            state={"question": question, "context_size": context_size},
            questions={
                "action": Choice(
                    instructions="How should this question be handled?",
                    criteria={
                        "local_retrieve": "Simple lookup, no synthesis needed",
                        "llm_synthesize": "Needs reasoning across multiple sources",
                        "stop": "Enough information has been gathered",
                    },
                )
            },
        )
        answer = result.choices["action"]
        return answer.choice, answer.probabilities

    def quality_score(self, text: str) -> float:
        """
        Rate the quality of a text passage on a scale.

        Args:
            text: The text to evaluate.

        Returns:
            Score value (float).
        """
        result = self.client.system_one(
            state={"text": text[:3000]},
            questions={
                "quality": Score(
                    instructions="Rate the scientific quality of this text",
                    criteria=["poor", "below_average", "average", "good", "excellent"],
                )
            },
        )
        return result.scores["quality"].score
