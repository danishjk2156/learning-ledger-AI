"""
Learning Ledger — main entry point.

An AI that remembers what you learn from papers and tells you when it becomes wrong.

Usage:
    uv run python -m src.main

Commands:
    drop        — Ingest a PDF into the knowledge base
    ask         — Ask a question about your papers
    learn       — Record something you learned
    claims      — View your learning ledger
    revalidate  — Re-check all claims for retractions and support decay
    check       — Check retraction/version status for a DOI
    sources     — List all ingested paper sources
    help        — Show this help
    quit        — Exit
"""

import os
import sys

from dotenv import load_dotenv

# Load .env before any other imports that need API keys
load_dotenv()

from .llm import LLMClient
from .decisions import DecisionGate
from .retriever import Retriever
from .ledger import init_ledger
from .integrity.retraction import init_retraction_db
from .tools import (
    DropPaperParams,
    AskQuestionParams,
    LearnClaimParams,
    ListClaimsParams,
    RevalidateParams,
    CheckDOIParams,
    execute_drop_paper,
    execute_ask_question,
    execute_learn_claim,
    execute_list_claims,
    execute_revalidate,
    execute_check_doi,
)


BANNER = r"""
  ╔══════════════════════════════════════════════════╗
  ║           📚 Learning Ledger v0.1.0              ║
  ║   Remembers what you learn. Tells you when       ║
  ║   it becomes wrong.                               ║
  ╚══════════════════════════════════════════════════╝
"""

HELP_TEXT = """
  Commands:
    drop        Ingest a PDF into the knowledge base
    ask         Ask a question about your papers
    learn       Record something you learned (with source quote)
    claims      View your learning ledger
    revalidate  Re-check all claims for retractions & support decay
    check       Check retraction/version status for a DOI
    sources     List all ingested paper sources
    help        Show this help
    quit        Exit
"""


def main():
    """Main entry point for Learning Ledger."""
    print(BANNER)

    # ── Initialize components ──
    print("  Initializing...")

    # Check for required API keys
    missing_keys = []
    if not os.getenv("GOOGLE_API_KEY"):
        missing_keys.append("GOOGLE_API_KEY")
    if not os.getenv("OPENROUTER_API_KEY"):
        missing_keys.append("OPENROUTER_API_KEY")

    if missing_keys:
        print(f"\n  ❌ Missing API keys: {', '.join(missing_keys)}")
        print("  Copy .env.example to .env and fill in your keys.")
        print("  See README.md for details.\n")
        sys.exit(1)

    try:
        llm = LLMClient()
        print("  ✅ LLM: Gemini 3.8 Flash")
    except Exception as e:
        print(f"  ❌ LLM init failed: {e}")
        sys.exit(1)

    try:
        jev = DecisionGate()
        print("  ✅ Decisions: Jev 1.13 (via OpenRouter)")
    except Exception as e:
        print(f"  ❌ Jev init failed: {e}")
        sys.exit(1)

    try:
        retriever = Retriever()
        chunk_count = retriever.count()
        print(f"  ✅ Vector store: {chunk_count} chunks indexed")
    except Exception as e:
        print(f"  ❌ ChromaDB init failed: {e}")
        sys.exit(1)

    # Initialize databases
    init_ledger()
    print("  ✅ Ledger: SQLite ready")

    try:
        init_retraction_db()
        print("  ✅ Retraction Watch: loaded")
    except Exception as e:
        print(f"  ⚠️  Retraction Watch: {e} (will use Crossref API only)")

    print(HELP_TEXT)

    # ── Shared components for tools ──
    components = {
        "retriever": retriever,
        "llm": llm,
        "jev": jev,
    }

    # ── Interactive loop ──
    while True:
        try:
            cmd = input("📚 > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n\nGoodbye! 👋")
            break

        if not cmd:
            continue

        if cmd == "quit" or cmd == "exit":
            print("\nGoodbye! 👋")
            break

        elif cmd == "help":
            print(HELP_TEXT)

        elif cmd == "drop":
            path = input("  PDF path: ").strip()
            if not path:
                print("  ❌ No path provided.")
                continue
            doi = input("  DOI (optional, press Enter to skip): ").strip()
            title = input("  Title (optional, press Enter to skip): ").strip()
            params = DropPaperParams(pdf_path=path, doi=doi, title=title)
            result = execute_drop_paper(params, **components)
            print(f"\n{result}\n")

        elif cmd == "ask":
            question = input("  Question: ").strip()
            if not question:
                print("  ❌ No question provided.")
                continue
            params = AskQuestionParams(question=question)
            print("\n  Searching and synthesizing...\n")
            result = execute_ask_question(params, **components)
            print(f"\n{result}\n")

        elif cmd == "learn":
            claim = input("  What did you learn? ").strip()
            if not claim:
                print("  ❌ No claim provided.")
                continue
            quote = input("  Exact quote from paper: ").strip()
            doi = input("  DOI (optional): ").strip()
            title = input("  Paper title (optional): ").strip()
            page_str = input("  Page number (optional, 0 for unknown): ").strip()
            page = int(page_str) if page_str.isdigit() else 0

            params = LearnClaimParams(
                claim=claim, quote=quote, doi=doi, title=title, page=page
            )
            result = execute_learn_claim(params, **components)
            print(f"\n{result}\n")

        elif cmd == "claims":
            status = input(
                "  Filter by status (active/suspect/retracted, or Enter for all): "
            ).strip()
            params = ListClaimsParams(status=status)
            result = execute_list_claims(params, **components)
            print(f"\n{result}\n")

        elif cmd == "revalidate":
            print("\n  Re-validating all active claims...\n")
            params = RevalidateParams()
            result = execute_revalidate(params, **components)
            print(f"\n{result}\n")

        elif cmd == "check":
            doi = input("  DOI to check: ").strip()
            if not doi:
                print("  ❌ No DOI provided.")
                continue
            params = CheckDOIParams(doi=doi)
            result = execute_check_doi(params, **components)
            print(f"\n{result}\n")

        elif cmd == "sources":
            sources = retriever.list_sources()
            if sources:
                print(f"\n  📚 {len(sources)} source(s) ingested:")
                for s in sources:
                    print(f"    • {s}")
            else:
                print("\n  📭 No papers ingested yet.")
            print()

        else:
            print(f"  Unknown command: '{cmd}'. Type 'help' for available commands.")


if __name__ == "__main__":
    main()
