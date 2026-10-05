"""
OpenHarness Tool Definitions — each user action is a typed tool.

Tools:
  - drop_paper: Ingest a PDF into the knowledge base
  - ask_question: Ask a question against ingested papers
  - learn_claim: Record something you learned
  - list_claims: View your learning ledger
  - revalidate_claims: Re-check all claims for integrity
  - check_doi: Look up retraction/version status for a DOI
"""

from pydantic import BaseModel, Field


# ── Parameter Schemas ──


class DropPaperParams(BaseModel):
    """Parameters for ingesting a paper."""

    pdf_path: str = Field(description="Path to the PDF file to ingest")
    doi: str = Field(default="", description="DOI of the paper (optional)")
    title: str = Field(default="", description="Title of the paper (optional)")


class AskQuestionParams(BaseModel):
    """Parameters for asking a question."""

    question: str = Field(description="The research question to answer")
    n_results: int = Field(
        default=5, description="Number of chunks to retrieve (1-20)"
    )


class LearnClaimParams(BaseModel):
    """Parameters for recording a claim."""

    claim: str = Field(description="What you learned, in your own words")
    quote: str = Field(description="The exact quote from the paper that supports this")
    doi: str = Field(default="", description="DOI of the source paper")
    title: str = Field(default="", description="Title of the source paper")
    page: int = Field(default=0, description="Page number of the quote")


class ListClaimsParams(BaseModel):
    """Parameters for listing claims."""

    status: str = Field(
        default="",
        description="Filter by status: 'active', 'suspect', 'retracted', or empty for all",
    )


class RevalidateParams(BaseModel):
    """Parameters for revalidation (no args needed)."""

    pass


class CheckDOIParams(BaseModel):
    """Parameters for checking a DOI."""

    doi: str = Field(description="The DOI to check (e.g., 10.1038/s41586-020-2649-2)")


# ── Tool Implementations ──
# These are standalone functions that can be called by the OpenHarness agent
# or directly from the CLI. Each function receives the shared components
# (retriever, jev, llm) via the tool registry.


def execute_drop_paper(params: DropPaperParams, retriever, **kwargs) -> str:
    """Ingest a PDF into the knowledge base."""
    from .ingest import ingest

    try:
        result = ingest(
            pdf_path=params.pdf_path,
            retriever=retriever,
            doi=params.doi,
            title=params.title,
        )
        return (
            f"✅ Paper ingested!\n"
            f"   Source: {result.get('source', params.pdf_path)}\n"
            f"   Pages: {result['pages']}\n"
            f"   Chunks stored: {result['chunks_stored']}\n"
            f"   DOI: {params.doi or 'not provided'}"
        )
    except FileNotFoundError:
        return f"❌ File not found: {params.pdf_path}"
    except ValueError as e:
        return f"❌ {e}"
    except Exception as e:
        return f"❌ Ingestion failed: {e}"


from .classifier import get_classifier


def execute_ask_question(
    params: AskQuestionParams, retriever, llm, return_sources: bool = False, **kwargs
):
    """
    Ask a question. Uses local Granite Question Classifier to route query:
    - If conversational: answers directly without querying ChromaDB papers.
    - If paper_query: performs vector search in ChromaDB and returns grounded citations.
    """
    intent = get_classifier().classify(params.question)

    if intent == "conversational":
        answer = llm.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are Learning Ledger AI, an intelligent research assistant designed to remember "
                        "what researchers learn from scientific papers and alert them when findings become wrong or retracted. "
                        "Respond warmly, conversationally, and concisely. If the user greets you or asks who you are, "
                        "introduce yourself and invite them to ask questions about their ingested papers."
                    ),
                },
                {"role": "user", "content": params.question},
            ]
        )
        if return_sources:
            return answer, []
        return answer

    if retriever.count() == 0:
        msg = "📭 No papers ingested yet. Use 'drop' (CLI) or 'Ingest & Embed Paper' (Web) to add a paper first."
        if return_sources:
            return msg, []
        return msg

    # Detect overview / tutorial questions
    q_lower = params.question.lower()
    is_overview = any(
        kw in q_lower
        for kw in [
            "explain", "teach", "summarize", "summary", "overview",
            "what is this paper", "about the paper", "recent paper", "tell me about",
            "what does the paper say", "beginner", "introduce", "library",
        ]
    )

    # Use more chunks for overviews to provide complete picture
    n_chunks = max(params.n_results or 5, 8) if is_overview else (params.n_results or 5)

    # Query expansion for broad overview questions
    search_query = params.question
    if is_overview and len(params.question.split()) <= 10:
        search_query = f"{params.question} abstract introduction methodology results deepfake"

    from .ingest import is_license_chunk

    chunks, metas = retriever.query(search_query, n_results=n_chunks)

    # Filter out empty, tiny, or license boilerplate chunks
    filtered_chunks = []
    filtered_metas = []
    for chunk, meta in zip(chunks, metas):
        if len(chunk.strip()) < 80 or is_license_chunk(chunk):
            continue
        filtered_chunks.append(chunk)
        filtered_metas.append(meta)

    chunks, metas = filtered_chunks, filtered_metas

    if not chunks:
        msg = "🔍 No relevant chunks found in your indexed papers for this question."
        if return_sources:
            return msg, []
        return msg

    # Build context from retrieved chunks
    context_parts = []
    for chunk, meta in zip(chunks, metas):
        source = meta.get("source", "unknown")
        page = meta.get("page", "?")
        context_parts.append(f"[{source}, p.{page}]\n{chunk}")

    context = "\n\n---\n\n".join(context_parts)

    if is_overview:
        system_instruction = (
            "You are an expert scientific research tutor. Your goal is to explain the research paper "
            "clearly, thoroughly, and accessibly based on the provided excerpts.\n\n"
            "Structure your response with clear, visually appealing sections:\n"
            "### 📌 1. Core Problem & Motivation\n"
            "What critical challenge or question does this research tackle?\n\n"
            "### 🔬 2. Key Techniques & Methodology\n"
            "How does the proposed solution or system work? What models, algorithms, or approaches are highlighted?\n\n"
            "### 📊 3. Findings & Performance\n"
            "What did the authors discover or prove? Highlight key statistics, metrics, or benchmarks.\n\n"
            "### 💡 4. Key Takeaways\n"
            "What is the most important lesson or takeaway from this work?\n\n"
            "Formatting Rules:\n"
            "- Always cite source pages using [Source, p.X] tags.\n"
            "- Use bolding for technical concepts.\n"
            "- Never mention copyright or download disclaimer text."
        )
    else:
        system_instruction = (
            "You are a helpful research assistant. Answer the user's question clearly and directly "
            "using the provided context from the research papers.\n"
            "- Use structured bullet points, clear bold headings, and clean formatting.\n"
            "- Always cite source pages using [Source, p.X] tags.\n"
            "- If the context only partially covers the question, synthesize all known facts and suggest relevant follow-up topics."
        )

    # Ask the LLM
    answer = llm.chat(
        [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {params.question}"},
        ]
    )

    sources = [
        {"text": chunk, "meta": meta} for chunk, meta in zip(chunks, metas)
    ]
    if return_sources:
        return answer, sources

    source_names = sorted(set(m.get("source", "?") for m in metas))
    return f"{answer}\n\n📚 Sources: {', '.join(source_names)}"


def execute_learn_claim(params: LearnClaimParams, jev, llm, **kwargs) -> str:
    """Record something you learned from a paper."""
    from .ledger import record_claim

    source = {
        "quote": params.quote,
        "doi": params.doi,
        "title": params.title,
        "page": params.page,
    }

    entry = record_claim(params.claim, source, jev, llm)

    status_icon = "✅" if entry["status"] == "active" else "⚠️"
    result = (
        f"{status_icon} Claim recorded!\n"
        f"   ID: {entry['claim_id']}\n"
        f"   Confidence: {entry['confidence']:.0%}\n"
        f"   Status: {entry['status']}"
    )

    if entry.get("note"):
        result += f"\n   Note: {entry['note'][:200]}"

    return result


def execute_list_claims(params: ListClaimsParams, **kwargs) -> str:
    """List claims in the ledger."""
    from .ledger import get_all_claims
    from .notify import format_claim_summary

    status_filter = params.status if params.status else None
    claims = get_all_claims(status=status_filter)
    return format_claim_summary(claims)


def execute_revalidate(params: RevalidateParams, jev, **kwargs) -> str:
    """Re-validate all active claims."""
    from .revalidate import revalidate_ledger
    from .notify import notify_user

    flagged = revalidate_ledger(jev)
    return notify_user(flagged)


def execute_check_doi(params: CheckDOIParams, **kwargs) -> str:
    """Check retraction and version status for a DOI."""
    from .integrity.retraction import check_retraction
    from .integrity.version import check_versions

    ret = check_retraction(params.doi)
    ver = check_versions(params.doi)

    lines = [f"🔍 DOI: {params.doi}\n"]

    # Retraction status
    if ret["status"] == "retracted":
        lines.append(f"   🚫 RETRACTED: {ret.get('reason', 'Unknown')}")
        lines.append(f"      Date: {ret.get('date', 'Unknown')}")
        lines.append(f"      Source: {ret.get('source', 'Unknown')}")
    elif ret["status"] == "corrected":
        lines.append(f"   ⚠️  CORRECTED: {ret.get('reason', 'Unknown')}")
    elif ret["status"] == "ok":
        lines.append("   ✅ Not retracted or corrected")
    else:
        lines.append("   ❓ Retraction status unknown")

    # Version info
    if ver["status"] == "ok":
        lines.append(f"\n   📄 Type: {ver.get('type', 'unknown')}")
        lines.append(f"   📅 Published: {ver.get('publication_date', 'unknown')}")
        lines.append(f"   📊 Citations: {ver.get('cited_by_count', 0)}")
        if ver.get("is_retracted"):
            lines.append("   🚫 Marked retracted on OpenAlex")
        if ver.get("title"):
            lines.append(f"   📝 Title: {ver['title']}")

    return "\n".join(lines)
