"""
Ingestion Pipeline — PDF → text → semantic chunks → embed → store in ChromaDB.

Implements header-based semantic chunking with document structure awareness
and license/watermark content filtering.
"""

import hashlib
import os
import re
from pypdf import PdfReader
from .retriever import Retriever

CHUNK_SIZE = 1000  # characters per sub-chunk (~150-180 words)
CHUNK_OVERLAP = 200  # overlap between sub-chunks
MAX_FILE_SIZE_MB = 50  # reject files larger than this


def clean_academic_watermarks(text: str) -> str:
    """
    Remove repetitive publisher banners, download notices, and copyright footers
    (e.g., IEEE Xplore, ScienceDirect, Springer) that contaminate vector retrieval.
    """
    lines = text.split("\n")
    clean_lines = [
        line for line in lines
        if "downloaded on" not in line.lower()
        and "restrictions apply" not in line.lower()
        and "authorized licensed use" not in line.lower()
        and "ieee xplore" not in line.lower()
        and "personal use is permitted" not in line.lower()
        and "permission must be obtained" not in line.lower()
    ]
    return "\n".join(clean_lines)


def is_license_chunk(text: str) -> bool:
    """
    Detect chunks that are predominantly license/header/publisher boilerplate.
    Matches IEEE, Springer, Elsevier, Wiley, and ACM digital library banners.
    """
    license_markers = [
        "downloaded on",
        "restrictions apply",
        "authorized licensed use",
        "ieee xplore",
        "©",
        "copyright",
        "all rights reserved",
        "personal use is permitted",
        "permission must be obtained",
        "conference publication",
        "institute of science & tech",
        "digital library",
    ]
    text_lower = text.lower()
    marker_count = sum(1 for m in license_markers if m in text_lower)
    return marker_count >= 2


def sub_split_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """
    Sub-split large section text by paragraphs, sentences, or word boundaries.
    """
    if len(text) <= chunk_size:
        return [text.strip()] if text.strip() else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            # Prefer paragraph breaks
            para = text.rfind("\n\n", start, end)
            if para > start + chunk_size // 2:
                end = para + 2
            else:
                # Prefer sentence breaks
                for sep in [". ", ".\n", "? ", "! "]:
                    sent = text.rfind(sep, start, end)
                    if sent > start + chunk_size // 2:
                        end = sent + len(sep)
                        break
                else:
                    # Prefer word breaks
                    space = text.rfind(" ", start, end)
                    if space > start + chunk_size // 2:
                        end = space + 1

        sub = text[start:end].strip()
        if sub:
            chunks.append(sub)

        start = end - chunk_overlap if end < len(text) else end

    return chunks


def semantic_chunk(
    text: str,
    source: str,
    page: int,
    doi: str = "",
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    """
    Header-based semantic chunking with metadata.
    Splits text on document structure (headings, sections), then sub-splits
    by size with overlap, and discards license-only fragments.
    """
    # 1. Clean publisher and download watermarks
    cleaned = clean_academic_watermarks(text)

    # 2. Split on section headers (markdown hashes, numbered sections, or standard academic headers)
    header_regex = r'\n(?=#{1,3}\s|[I|V|X]+\.\s+[A-Z]|\d+\.\s+[A-Z]|(?:ABSTRACT|INTRODUCTION|RELATED WORK|METHODOLOGY|SYSTEM MODEL|EXPERIMENTS|RESULTS|DISCUSSION|CONCLUSION|REFERENCES)[\s—\:\n])'
    sections = re.split(header_regex, cleaned, flags=re.IGNORECASE)

    chunks = []
    for section in sections:
        section_text = section.strip()
        if len(section_text) < 50:
            continue  # Skip tiny fragments

        # Extract first line (up to 80 chars) as section label
        section_label = section_text.split("\n", 1)[0][:80].strip()

        # 3. Sub-split large sections
        sub_chunks = sub_split_text(section_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        for sub in sub_chunks:
            # Skip license boilerplate chunks
            if is_license_chunk(sub):
                continue

            chunks.append({
                "text": sub,
                "metadata": {
                    "doi": doi,
                    "source": source,
                    "page": page,
                    "section": section_label,
                    "chunk_type": "header" if sub.startswith(("#", "1.", "I.", "Abstract")) else "content",
                },
            })

    return chunks


def ingest(
    pdf_path: str,
    retriever: Retriever,
    doi: str = "",
    title: str = "",
) -> dict:
    """
    Ingest a PDF into the vector store with semantic chunking and metadata.

    Extracts text from each page, chunks it semantically by headers,
    filters out license notices, and stores chunks with metadata in ChromaDB.

    Args:
        pdf_path: Path to the PDF file.
        retriever: Retriever instance to store chunks in.
        doi: DOI of the paper (optional but recommended).
        title: Title of the paper (falls back to filename).

    Returns:
        Dict with ingestion stats: pages, chunks_stored, source, doi.
    """
    # Validate file
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(
            f"PDF too large ({file_size_mb:.1f}MB > {MAX_FILE_SIZE_MB}MB limit)"
        )

    # Use filename as default title
    if not title:
        title = os.path.splitext(os.path.basename(pdf_path))[0]

    # Extract text from PDF
    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        raise RuntimeError(f"Failed to read PDF: {e}")

    all_chunks = []
    all_metas = []
    all_ids = []

    for page_num, page in enumerate(reader.pages):
        try:
            raw_text = page.extract_text() or ""
        except Exception:
            continue

        if not raw_text.strip():
            continue

        page_chunks = semantic_chunk(
            text=raw_text,
            source=title,
            page=page_num + 1,
            doi=doi,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )

        for i, item in enumerate(page_chunks):
            chunk_id = hashlib.sha256(
                f"{pdf_path}:{page_num}:{i}:{item['metadata'].get('section', '')}".encode()
            ).hexdigest()[:16]

            all_chunks.append(item["text"])
            all_metas.append(item["metadata"])
            all_ids.append(chunk_id)

    if not all_chunks:
        return {"pages": len(reader.pages), "chunks_stored": 0, "warning": "No text extracted"}

    # Batch add to ChromaDB (batches of 50 to respect Gemini embedding rate limits)
    batch_size = 50
    stored = 0
    for i in range(0, len(all_chunks), batch_size):
        batch_end = i + batch_size
        retriever.add(
            chunks=all_chunks[i:batch_end],
            metadatas=all_metas[i:batch_end],
            ids=all_ids[i:batch_end],
        )
        stored += len(all_chunks[i:batch_end])

    return {
        "pages": len(reader.pages),
        "chunks_stored": stored,
        "source": title,
        "doi": doi,
    }
