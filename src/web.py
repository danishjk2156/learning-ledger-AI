"""
Learning Ledger — Web Dashboard API Server.

Serves the modern glassmorphic dashboard and exposes REST endpoints
for all ledger capabilities (drop, ask, learn, claims, revalidate, check).
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from .integrity.retraction import check_retraction, init_retraction_db
from .integrity.version import check_versions
from .ledger import get_all_claims, get_claim, init_ledger, update_claim_status
from .tools import (
    AskQuestionParams,
    CheckDOIParams,
    DropPaperParams,
    LearnClaimParams,
    ListClaimsParams,
    RevalidateParams,
    execute_ask_question,
    execute_check_doi,
    execute_drop_paper,
    execute_learn_claim,
    execute_list_claims,
    execute_revalidate,
)

app = FastAPI(title="Learning Ledger API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
LIBRARY_DIR = Path("library")
LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

import traceback

# Lazy-loaded shared components
_components = {"llm": None, "jev": None, "retriever": None}
_init_errors = {"retriever": None, "llm": None, "jev": None}


def get_components():
    """Lazily initialize core components to handle missing keys gracefully."""
    global _components, _init_errors
    load_dotenv(override=True)

    import importlib

    if _components["retriever"] is None:
        try:
            init_ledger()
            try:
                init_retraction_db()
            except Exception as e:
                print(f"[Web] Retraction Watch local DB notice: {e}")

            import src.embedder
            import src.retriever
            importlib.reload(src.embedder)
            importlib.reload(src.retriever)

            _components["retriever"] = src.retriever.Retriever()
            _init_errors["retriever"] = None
        except Exception as e:
            traceback.print_exc()
            _init_errors["retriever"] = f"Retriever init failed: {e}"

    if _components["llm"] is None and os.getenv("GOOGLE_API_KEY"):
        try:
            import src.llm
            importlib.reload(src.llm)

            _components["llm"] = src.llm.LLMClient()
            _init_errors["llm"] = None
        except Exception as e:
            traceback.print_exc()
            _init_errors["llm"] = f"LLM init failed: {e}"

    if _components["jev"] is None and os.getenv("OPENROUTER_API_KEY"):
        try:
            import src.decisions
            importlib.reload(src.decisions)

            _components["jev"] = src.decisions.DecisionGate()
            _init_errors["jev"] = None
        except Exception as e:
            traceback.print_exc()
            _init_errors["jev"] = f"Jev init failed: {e}"

    return _components


# ── Pydantic Request Models ──


class LearnRequest(BaseModel):
    claim: str
    quote: str
    doi: Optional[str] = ""
    title: Optional[str] = ""
    page: Optional[int] = 0


class AskRequest(BaseModel):
    question: str
    n_results: Optional[int] = 5


class StatusUpdateRequest(BaseModel):
    status: str
    note: Optional[str] = None


# ── API Routes ──


@app.get("/api/status")
def get_system_status():
    """Check system health, API key presence, and component status."""
    has_google = bool(os.getenv("GOOGLE_API_KEY"))
    has_openrouter = bool(os.getenv("OPENROUTER_API_KEY"))
    comps = get_components()

    return {
        "ok": has_google and has_openrouter,
        "keys": {
            "GOOGLE_API_KEY": has_google,
            "OPENROUTER_API_KEY": has_openrouter,
            "OPENALEX_API_KEY": bool(os.getenv("OPENALEX_API_KEY")),
            "UNPAYWALL_EMAIL": bool(os.getenv("UNPAYWALL_EMAIL")),
        },
        "components": {
            "retriever": comps["retriever"] is not None,
            "llm": comps["llm"] is not None,
            "jev": comps["jev"] is not None,
        },
        "errors": _init_errors,
        "error": _init_errors.get("retriever") or _init_errors.get("llm") or _init_errors.get("jev"),
    }


@app.get("/api/stats")
def get_stats():
    """Return dashboard counters."""
    comps = get_components()
    retriever = comps.get("retriever")
    chunk_count = retriever.count() if retriever else 0
    sources = retriever.list_sources() if retriever else []

    claims = get_all_claims()
    active_count = sum(1 for c in claims if c.get("status") == "active")
    suspect_count = sum(1 for c in claims if c.get("status") == "suspect")
    retracted_count = sum(1 for c in claims if c.get("status") == "retracted")

    return {
        "chunks_indexed": chunk_count,
        "papers_count": len(sources),
        "total_claims": len(claims),
        "active_claims": active_count,
        "suspect_claims": suspect_count,
        "retracted_claims": retracted_count,
        "sources": sources,
    }


@app.get("/api/claims")
def list_claims(status: Optional[str] = None):
    """Retrieve all claims, optionally filtered by status."""
    return get_all_claims(status=status if status else None)


@app.post("/api/learn")
def create_claim(req: LearnRequest):
    """Record a claim with Jev verification."""
    comps = get_components()
    if not comps["jev"]:
        raise HTTPException(
            status_code=400,
            detail="OPENROUTER_API_KEY is not set or Jev client failed to initialize.",
        )
    if not comps["llm"]:
        raise HTTPException(
            status_code=400,
            detail="GOOGLE_API_KEY is not set or LLM client failed to initialize.",
        )

    params = LearnClaimParams(
        claim=req.claim,
        quote=req.quote,
        doi=req.doi or "",
        title=req.title or "",
        page=req.page or 0,
    )
    result_text = execute_learn_claim(
        params, jev=comps["jev"], llm=comps["llm"]
    )
    # Fetch recent claims to return the full stored object
    all_claims = get_all_claims()
    latest = all_claims[0] if all_claims else {}
    return {"message": result_text, "claim": latest}


@app.patch("/api/claims/{claim_id}")
def update_claim(claim_id: str, req: StatusUpdateRequest):
    """Update claim status."""
    claim = get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    update_claim_status(claim_id, req.status, note=req.note)
    return {"ok": True, "claim_id": claim_id, "status": req.status}


@app.post("/api/ask")
def ask_question(req: AskRequest):
    """Ask a question against ingested papers."""
    comps = get_components()
    if not comps["retriever"]:
        raise HTTPException(status_code=400, detail="Vector store not initialized.")
    if not comps["llm"]:
        raise HTTPException(
            status_code=400, detail="GOOGLE_API_KEY is not configured."
        )

    try:
        params = AskQuestionParams(question=req.question, n_results=req.n_results or 5)
        answer, sources = execute_ask_question(
            params, retriever=comps["retriever"], llm=comps["llm"], return_sources=True
        )
        return {
            "answer": answer,
            "sources": sources,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/drop")
async def drop_paper(
    file: Optional[UploadFile] = File(None),
    path: Optional[str] = Form(None),
    doi: Optional[str] = Form(""),
    title: Optional[str] = Form(""),
):
    """Ingest a paper PDF either by file upload or local file path."""
    comps = get_components()
    if not comps["retriever"]:
        err_msg = _init_errors.get("retriever") or "Vector store not initialized."
        raise HTTPException(status_code=400, detail=f"Vector store not initialized: {err_msg}")

    target_path = None
    if file and file.filename:
        # Save uploaded file to library/
        dest = LIBRARY_DIR / file.filename
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        target_path = str(dest)
        if not title:
            title = file.filename
    elif path:
        target_path = path
    else:
        raise HTTPException(status_code=400, detail="No file or path provided.")

    params = DropPaperParams(pdf_path=target_path, doi=doi or "", title=title or "")
    result = execute_drop_paper(params, retriever=comps["retriever"])
    return {"message": result, "file": target_path}


@app.post("/api/reindex")
def reindex_library():
    """
    Purge legacy vector store collection and re-index all papers in library/
    using header-based semantic chunking and license filters.
    """
    comps = get_components()
    retriever = comps.get("retriever")
    if not retriever:
        raise HTTPException(status_code=400, detail="Vector store not initialized.")

    from .ingest import ingest

    # Reset collection in ChromaDB
    retriever.reset_collection()

    pdf_files = list(LIBRARY_DIR.glob("*.pdf"))
    if not pdf_files:
        return {
            "status": "empty",
            "message": "Vector store wiped. No PDF files found in library/ directory to re-index.",
            "total_chunks": 0,
        }

    reindexed = []
    for pdf in pdf_files:
        try:
            res = ingest(
                pdf_path=str(pdf),
                retriever=retriever,
                title=pdf.name,
            )
            reindexed.append(res)
        except Exception as e:
            reindexed.append({"file": pdf.name, "error": str(e)})

    return {
        "status": "success",
        "message": f"Purged contaminated chunks and re-indexed {len(reindexed)} paper(s) with clean semantic chunking.",
        "results": reindexed,
        "total_chunks": retriever.count(),
    }


@app.post("/api/revalidate")
def revalidate():
    """Trigger claim revalidation against Retraction Watch and semantic decay."""
    comps = get_components()
    if not comps["jev"]:
        raise HTTPException(
            status_code=400, detail="OPENROUTER_API_KEY required for Jev revalidation."
        )

    from .notify import notify_user
    from .revalidate import revalidate_ledger

    flagged = revalidate_ledger(comps["jev"])
    formatted = notify_user(flagged)
    return {"flagged": flagged, "report": formatted}


@app.get("/api/check-doi")
def inspect_doi(doi: str):
    """Live inspect a DOI for retraction status, corrections, and OpenAlex metadata."""
    if not doi:
        raise HTTPException(status_code=400, detail="DOI parameter required.")
    params = CheckDOIParams(doi=doi)
    text = execute_check_doi(params)
    ret = check_retraction(doi)
    ver = check_versions(doi)
    return {"formatted": text, "retraction": ret, "version": ver}


# ── Mount Frontend Static Files ──
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return {"message": "Learning Ledger Web API running. Frontend building..."}
    return FileResponse(index_file)


def run():
    """CLI launcher for the web dashboard."""
    import uvicorn

    print("🚀 Starting Learning Ledger Web Dashboard...")
    print("👉 Open your browser at http://localhost:8000")
    uvicorn.run("src.web:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    run()
