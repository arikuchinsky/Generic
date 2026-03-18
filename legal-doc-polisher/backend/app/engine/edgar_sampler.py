"""EDGAR Self-Test Pipeline — Sub-Application for Rigorous Testing.

This is a standalone testing pipeline that:
1. Downloads 100 real legal documents from SEC EDGAR (10 chunks x 10 docs)
2. Runs the polisher on each document
3. Analyzes patterns and failures per chunk
4. Uses findings from each chunk to improve detection in subsequent chunks
5. Generates a comprehensive improvement report with actionable recommendations
6. Feeds new examples into the learning system for recursive improvement

Architecture:
    Chunk 1 (10 docs) → analyze → learn → update rules
    Chunk 2 (10 docs) → analyze → learn → update rules (with chunk 1 learnings)
    ...
    Chunk 10 (10 docs) → analyze → learn → final report

Usage:
    python -m app.engine.edgar_sampler
    python -m app.engine.edgar_sampler --chunks 10 --per-chunk 10 --output ./results
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from ..config import settings
from ..models.enums import DocumentType, FocusArea
from ..models.schemas import Change, Example, PrePolishOptions
from .orchestrator import polish_document
from .profiler import build_style_profile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# EDGAR Configuration
# ---------------------------------------------------------------------------

# EDGAR full-text search endpoint
EDGAR_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"

# User-Agent required by SEC (must include company name and email)
EDGAR_HEADERS = {
    "User-Agent": "LegalDocPolisher/0.1.0 (selftest@legaldocpolisher.dev)",
    "Accept-Encoding": "gzip, deflate",
}

# CRE-focused search terms — expanded set to ensure we can find 100 documents
# Each search term targets a different type of CRE legal document
CRE_SEARCH_TERMS = [
    # Chunk 1: Lease agreements
    "commercial lease agreement",
    "office lease",
    "retail lease agreement",
    # Chunk 2: Purchase/sale
    "real estate purchase agreement",
    "property sale agreement",
    "real property conveyance",
    # Chunk 3: Financing
    "deed of trust",
    "commercial mortgage",
    "loan agreement real estate",
    # Chunk 4: Management
    "property management agreement",
    "asset management agreement real estate",
    "facilities management contract",
    # Chunk 5: Ground lease / sublease
    "ground lease",
    "sublease agreement commercial",
    "master lease agreement",
    # Chunk 6: Assignments / assumptions
    "assignment and assumption agreement",
    "assignment of lease",
    "assumption agreement real property",
    # Chunk 7: Due diligence
    "estoppel certificate",
    "subordination non-disturbance and attornment",
    "tenant estoppel",
    # Chunk 8: Construction / development
    "construction contract commercial",
    "development agreement real estate",
    "architect agreement building",
    # Chunk 9: Joint ventures / partnerships
    "joint venture agreement real estate",
    "limited partnership agreement property",
    "operating agreement real estate",
    # Chunk 10: Miscellaneous CRE
    "easement agreement",
    "restrictive covenant commercial",
    "right of first refusal real estate",
]

# Well-known CRE REITs and real estate companies for fallback
CRE_COMPANY_CIKS = [
    "0000899629",  # Simon Property Group
    "0001063761",  # Prologis
    "0000036104",  # Equity Residential
    "0000803649",  # Boston Properties
    "0000790528",  # Vornado Realty Trust
    "0000060714",  # Mack-Cali Realty
    "0000879101",  # Regency Centers
    "0000885590",  # Kimco Realty
    "0001495240",  # CBRE Group
    "0001037540",  # JBG SMITH Properties
    "0001364250",  # Brookfield Asset Management
    "0001579298",  # American Realty Capital
    "0000798354",  # Hospitality Properties Trust
    "0000049196",  # Federal Realty Investment Trust
    "0000093410",  # Taubman Centers
    "0000828916",  # Public Storage
    "0000924901",  # Highwoods Properties
    "0000921082",  # Kilroy Realty
    "0000826675",  # Camden Property Trust
    "0000910108",  # Duke Realty
]


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class DocumentResult:
    """Result of processing a single document."""

    document_id: str
    filename: str
    source_url: str = ""
    status: str = "pending"  # pending, processing, success, error, skipped
    changes: list[dict] = field(default_factory=list)
    change_count: int = 0
    changes_by_category: dict[str, int] = field(default_factory=dict)
    changes_by_severity: dict[str, int] = field(default_factory=dict)
    processing_time_seconds: float = 0.0
    error_message: str = ""
    profile_summary: dict = field(default_factory=dict)

    # Validation results (false-positive prevention)
    validation_passed: bool = True
    validation_issues: list[dict] = field(default_factory=list)
    content_preserved: bool = True
    headers_preserved: bool = True
    footers_preserved: bool = True
    exhibits_preserved: bool = True

    # Per-document learnings
    learnings_generated: list[dict] = field(default_factory=list)
    glitches_caught: list[dict] = field(default_factory=list)
    glitches_introduced: list[dict] = field(default_factory=list)


@dataclass
class ChunkResult:
    """Result of processing one chunk of 10 documents."""

    chunk_number: int
    search_terms_used: list[str] = field(default_factory=list)
    documents: list[DocumentResult] = field(default_factory=list)
    total_documents: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    total_changes: int = 0
    aggregate_by_category: dict[str, int] = field(default_factory=dict)
    aggregate_by_severity: dict[str, int] = field(default_factory=dict)
    common_patterns: dict[str, int] = field(default_factory=dict)
    new_learnings: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    chunk_start_time: str = ""
    chunk_end_time: str = ""
    chunk_duration_seconds: float = 0.0


@dataclass
class PipelineResult:
    """Full pipeline result across all 10 chunks (100 documents)."""

    pipeline_id: str = ""
    start_time: str = ""
    end_time: str = ""
    total_duration_seconds: float = 0.0
    config: dict = field(default_factory=dict)
    chunks: list[ChunkResult] = field(default_factory=list)

    # Aggregate stats across all chunks
    total_documents: int = 0
    total_successful: int = 0
    total_failed: int = 0
    total_skipped: int = 0
    total_changes: int = 0
    grand_by_category: dict[str, int] = field(default_factory=dict)
    grand_by_severity: dict[str, int] = field(default_factory=dict)

    # Improvement tracking
    cumulative_learnings: list[dict] = field(default_factory=list)
    improvement_trajectory: list[dict] = field(default_factory=list)
    final_recommendations: list[str] = field(default_factory=list)
    rules_improvement_log: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# EDGAR Document Downloader
# ---------------------------------------------------------------------------


async def download_chunk_documents(
    client: httpx.AsyncClient,
    chunk_number: int,
    search_terms: list[str],
    output_dir: Path,
    docs_per_chunk: int = 10,
) -> list[tuple[Path, str]]:
    """Download documents for a single chunk.

    Args:
        client: HTTP client with EDGAR headers.
        chunk_number: Chunk number (1-indexed).
        search_terms: Search terms for this chunk.
        output_dir: Directory to save files.
        docs_per_chunk: Target number of documents.

    Returns:
        List of (file_path, source_url) tuples.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[tuple[Path, str]] = []

    # Strategy 1: Search by terms
    for term in search_terms:
        if len(downloaded) >= docs_per_chunk:
            break

        try:
            filing_urls = await _search_edgar_filings(client, term, limit=3)
            for url in filing_urls:
                if len(downloaded) >= docs_per_chunk:
                    break
                try:
                    path = await _download_and_save(client, url, output_dir, chunk_number)
                    if path:
                        downloaded.append((path, url))
                        logger.info(f"  Chunk {chunk_number}: Downloaded {path.name}")
                except Exception as e:
                    logger.debug(f"  Failed to download {url}: {e}")
                # EDGAR rate limit: max 10 req/sec
                await asyncio.sleep(0.15)
        except Exception as e:
            logger.debug(f"  Search failed for '{term}': {e}")

    # Strategy 2: Fallback to known CRE company filings
    if len(downloaded) < docs_per_chunk:
        start_idx = (chunk_number - 1) * 2
        fallback_ciks = CRE_COMPANY_CIKS[start_idx : start_idx + 4]

        for cik in fallback_ciks:
            if len(downloaded) >= docs_per_chunk:
                break
            try:
                urls = await _get_company_filings(client, cik, count=3)
                for url in urls:
                    if len(downloaded) >= docs_per_chunk:
                        break
                    try:
                        path = await _download_and_save(client, url, output_dir, chunk_number)
                        if path:
                            downloaded.append((path, url))
                    except Exception:
                        pass
                    await asyncio.sleep(0.15)
            except Exception:
                pass

    return downloaded


async def _search_edgar_filings(
    client: httpx.AsyncClient,
    query: str,
    limit: int = 3,
) -> list[str]:
    """Search EDGAR EFTS for filing documents matching a query."""
    params = {
        "q": f'"{query}"',
        "dateRange": "custom",
        "startdt": "2019-01-01",
        "enddt": "2025-12-31",
        "forms": "10-K,10-Q,8-K,S-11,ABS-EE,EX-10,EX-99",
    }

    resp = await client.get(EDGAR_EFTS_URL, params=params)
    if resp.status_code != 200:
        return []

    try:
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        urls = []
        for hit in hits[:limit]:
            source = hit.get("_source", {})
            url = source.get("file_url") or source.get("url")
            if url:
                if not url.startswith("http"):
                    url = f"https://www.sec.gov{url}"
                urls.append(url)
        return urls
    except Exception:
        return []


async def _get_company_filings(
    client: httpx.AsyncClient,
    cik: str,
    count: int = 3,
) -> list[str]:
    """Get recent filing URLs for a specific company via EDGAR JSON API."""
    # Use the EDGAR company submissions API
    padded_cik = cik.lstrip("0").zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"

    resp = await client.get(url)
    if resp.status_code != 200:
        return []

    try:
        data = resp.json()
        recent = data.get("filings", {}).get("recent", {})
        accession_numbers = recent.get("accessionNumber", [])[:count]
        primary_docs = recent.get("primaryDocument", [])[:count]

        urls = []
        for acc, doc in zip(accession_numbers, primary_docs):
            acc_formatted = acc.replace("-", "")
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc_formatted}/{doc}"
            urls.append(filing_url)

        return urls
    except Exception:
        return []


async def _download_and_save(
    client: httpx.AsyncClient,
    url: str,
    output_dir: Path,
    chunk_number: int,
) -> Path | None:
    """Download a document and save it to disk."""
    resp = await client.get(url, follow_redirects=True)
    if resp.status_code != 200:
        return None

    content = resp.text
    if len(content) < 500:
        return None  # Too small to be useful

    # Generate filename
    url_part = url.split("/")[-1] if "/" in url else "filing"
    safe_name = re.sub(r"[^\w\-.]", "_", url_part)[:40]
    suffix = ".htm"
    if url.endswith(".txt"):
        suffix = ".txt"
    elif url.endswith(".xml"):
        suffix = ".xml"

    filename = f"chunk{chunk_number:02d}_{safe_name}{suffix}"
    path = output_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Document Conversion (HTML/text → rough DOCX for testing)
# ---------------------------------------------------------------------------


def convert_to_test_docx(source_path: Path, output_path: Path) -> Path:
    """Convert an HTML/text filing to a .docx for testing.

    This creates a rough .docx that mimics the content and structure
    of the filing, which is sufficient for testing formatting rules.
    """
    from docx import Document
    from docx.shared import Pt, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    content = source_path.read_text(encoding="utf-8", errors="replace")

    # Strip HTML tags for a rough text extraction
    text = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL)
    text = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<h(\d)[^>]*>", r"\nHEADING\1:", text, flags=re.IGNORECASE)
    text = re.sub(r"</h\d>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    doc = Document()
    lines = text.strip().split("\n")
    paragraph_count = 0
    max_paragraphs = 200  # Cap for reasonable test size

    # Default body style
    default_font = "Times New Roman"
    default_size = 12

    # Intentionally introduce some formatting variations to test the rules
    import random
    rng = random.Random(hash(source_path.name))

    for line in lines:
        if paragraph_count >= max_paragraphs:
            break

        line = line.strip()
        if not line:
            continue

        # Detect headings
        heading_match = re.match(r"HEADING(\d):\s*(.*)", line)
        if heading_match:
            level = min(int(heading_match.group(1)), 4)
            heading_text = heading_match.group(2).strip()
            if heading_text:
                h = doc.add_heading(heading_text, level=level)
                for run in h.runs:
                    run.font.name = default_font
                    run.font.size = Pt(14 - (level - 1) * 2)
                    run.font.bold = True
                    # Randomly introduce formatting defects (10% chance per heading)
                    if rng.random() < 0.10:
                        run.font.name = rng.choice(["Calibri", "Arial", "Courier New"])
                    if rng.random() < 0.10:
                        run.font.bold = False
                paragraph_count += 1
                continue

        # Detect section-like headings from text patterns
        if re.match(r"^(ARTICLE|SECTION|EXHIBIT)\s+[IVXLCDM\d]+", line, re.IGNORECASE):
            h = doc.add_heading(line[:100], level=2)
            for run in h.runs:
                run.font.name = default_font
                run.font.size = Pt(12)
                run.font.bold = True
            paragraph_count += 1
            continue

        # Regular paragraph
        para = doc.add_paragraph(line[:500])
        for run in para.runs:
            run.font.name = default_font
            run.font.size = Pt(default_size)
        para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        # Randomly introduce formatting defects
        if rng.random() < 0.05:
            para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        if rng.random() < 0.05 and para.runs:
            para.runs[0].font.name = rng.choice(["Calibri", "Arial"])
        if rng.random() < 0.08:
            # Replace smart quotes with straight quotes
            for run in para.runs:
                run.text = run.text.replace("\u201C", '"').replace("\u201D", '"')

        paragraph_count += 1

    doc.save(str(output_path))
    return output_path


# ---------------------------------------------------------------------------
# Core Pipeline
# ---------------------------------------------------------------------------


async def process_single_document(
    docx_path: Path,
    doc_id: str,
    source_url: str,
    accumulated_examples: list[Example],
) -> tuple[DocumentResult, list[Example]]:
    """Process a single document and generate per-document learnings.

    Each document processed contributes learnings that improve the next document.
    Also validates that no new formatting glitches were introduced.

    Args:
        docx_path: Path to the .docx file.
        doc_id: Unique identifier for this document.
        source_url: Where this document came from.
        accumulated_examples: Examples accumulated from all previous documents.

    Returns:
        Tuple of (DocumentResult, new_examples_from_this_doc).
    """
    result = DocumentResult(
        document_id=doc_id,
        filename=docx_path.name,
        source_url=source_url,
    )
    new_examples: list[Example] = []

    start = time.time()
    try:
        result.status = "processing"
        options = PrePolishOptions(
            document_type=DocumentType.CONTRACT,
            focus_areas=[FocusArea.HEADINGS, FocusArea.QUOTES, FocusArea.LISTS, FocusArea.SPACING],
            notes="Self-test pipeline run",
        )

        report = await polish_document(
            job_id=f"selftest_{doc_id}",
            docx_path=docx_path,
            options=options,
            examples=accumulated_examples,
        )

        result.status = "success"
        result.change_count = report.total_changes
        result.changes_by_category = report.changes_by_category
        result.changes = [
            {
                "category": c.category,
                "description": c.description,
                "severity": c.severity.value if hasattr(c.severity, "value") else str(c.severity),
                "source": c.source.value if hasattr(c.source, "value") else str(c.source),
                "location": c.location,
            }
            for c in report.changes
        ]

        # Extract severity counts
        severity_counter: Counter = Counter()
        for c in report.changes:
            sev = c.severity.value if hasattr(c.severity, "value") else str(c.severity)
            severity_counter[sev] += 1
        result.changes_by_severity = dict(severity_counter)

        # Profile summary
        result.profile_summary = {
            "heading_levels_found": list(report.style_profile.heading_styles.keys()),
            "body_font": report.style_profile.body_font.name,
            "body_alignment": report.style_profile.body_alignment,
            "quote_style": report.style_profile.quote_style,
        }

        # --- VALIDATION: Check we didn't introduce new glitches ---
        polished_path = settings.jobs_dir / f"selftest_{doc_id}" / "polished.docx"
        if polished_path.exists():
            from .validator import validate_polish
            validation = validate_polish(docx_path, polished_path)

            result.validation_passed = validation.is_valid
            result.content_preserved = validation.content_preserved
            result.headers_preserved = validation.headers_preserved
            result.footers_preserved = validation.footers_preserved
            result.exhibits_preserved = validation.exhibits_preserved
            result.validation_issues = [
                {
                    "category": vi.category,
                    "location": vi.location,
                    "description": vi.description,
                    "severity": vi.severity,
                }
                for vi in validation.issues
            ]

            # Track glitches caught vs introduced
            result.glitches_caught = [
                c for c in result.changes
                if c.get("severity") in ("moderate", "major")
            ]
            result.glitches_introduced = [
                {
                    "category": vi.category,
                    "description": vi.description,
                    "severity": vi.severity,
                }
                for vi in validation.issues
                if vi.severity in ("error", "critical")
            ]

            if result.glitches_introduced:
                logger.warning(
                    f"  {doc_id}: INTRODUCED {len(result.glitches_introduced)} glitches! "
                    f"Content: {result.content_preserved}, Headers: {result.headers_preserved}, "
                    f"Footers: {result.footers_preserved}, Exhibits: {result.exhibits_preserved}"
                )

        # --- PER-DOCUMENT LEARNING ---
        # Generate examples from this document's processing results
        # so the next document benefits from what we learned here
        for change_dict in result.changes:
            cat = change_dict.get("category", "other")
            desc = change_dict.get("description", "")
            # Learn from moderate+ severity issues
            if change_dict.get("severity") in ("moderate", "major"):
                example = Example(
                    category=cat,
                    description=f"[Auto-learned from {doc_id}] {desc[:200]}",
                    document_type="contract",
                )
                new_examples.append(example)
                result.learnings_generated.append({
                    "category": cat,
                    "description": desc[:200],
                    "from_document": doc_id,
                })

        # Also learn from validation failures (what NOT to do)
        for glitch in result.glitches_introduced:
            new_examples.append(Example(
                category=glitch.get("category", "other"),
                description=(
                    f"[FALSE POSITIVE from {doc_id}] Polisher introduced: "
                    f"{glitch.get('description', '')[:200]}. Avoid this fix pattern."
                ),
                document_type="contract",
            ))

    except Exception as e:
        result.status = "error"
        result.error_message = str(e)[:500]
        logger.warning(f"Document {doc_id} failed: {e}")

    result.processing_time_seconds = round(time.time() - start, 2)
    return result, new_examples


async def process_chunk(
    chunk_number: int,
    chunk_terms: list[str],
    base_dir: Path,
    docs_per_chunk: int,
    accumulated_examples: list[Example],
) -> ChunkResult:
    """Process one chunk of documents.

    Downloads docs, converts to .docx, runs polisher, analyzes results.

    Args:
        chunk_number: Chunk number (1-10).
        chunk_terms: EDGAR search terms for this chunk.
        base_dir: Base output directory.
        docs_per_chunk: Number of documents per chunk.
        accumulated_examples: Learning examples from previous chunks.

    Returns:
        ChunkResult with full chunk analysis.
    """
    chunk_result = ChunkResult(
        chunk_number=chunk_number,
        search_terms_used=chunk_terms,
    )
    chunk_result.chunk_start_time = datetime.now().isoformat()
    chunk_start = time.time()

    chunk_dir = base_dir / f"chunk_{chunk_number:02d}"
    raw_dir = chunk_dir / "raw_downloads"
    docx_dir = chunk_dir / "docx_files"
    results_dir = chunk_dir / "results"
    for d in [raw_dir, docx_dir, results_dir]:
        d.mkdir(parents=True, exist_ok=True)

    logger.info(f"\n{'='*60}")
    logger.info(f"CHUNK {chunk_number}/10 — Downloading documents...")
    logger.info(f"{'='*60}")

    # Step 1: Download
    async with httpx.AsyncClient(headers=EDGAR_HEADERS, timeout=30.0) as client:
        downloads = await download_chunk_documents(
            client, chunk_number, chunk_terms, raw_dir, docs_per_chunk
        )

    logger.info(f"  Downloaded {len(downloads)} documents")

    # Step 2: Convert to .docx
    docx_files: list[tuple[Path, str]] = []
    for raw_path, source_url in downloads:
        try:
            docx_path = docx_dir / (raw_path.stem + ".docx")
            convert_to_test_docx(raw_path, docx_path)
            docx_files.append((docx_path, source_url))
        except Exception as e:
            logger.debug(f"  Conversion failed for {raw_path.name}: {e}")

    logger.info(f"  Converted {len(docx_files)} documents to .docx")

    # Step 3: Process each document WITH PER-DOCUMENT LEARNING
    # Each doc contributes learnings that improve the next doc in the chunk
    all_changes: list[dict] = []
    chunk_examples = list(accumulated_examples)  # Copy so we can grow per-doc

    for i, (docx_path, source_url) in enumerate(docx_files):
        doc_id = f"c{chunk_number:02d}_d{i+1:02d}"
        doc_num_global = (chunk_number - 1) * docs_per_chunk + i + 1
        logger.info(
            f"  Processing [{i+1}/{len(docx_files)}] {docx_path.name} "
            f"(doc #{doc_num_global}/100, {len(chunk_examples)} examples available)..."
        )

        doc_result, new_examples = await process_single_document(
            docx_path, doc_id, source_url, chunk_examples
        )
        chunk_result.documents.append(doc_result)

        if doc_result.status == "success":
            chunk_result.successful += 1
            all_changes.extend(doc_result.changes)

            # PROGRESSIVE LEARNING: Add this doc's examples for the next doc
            chunk_examples.extend(new_examples)
            logger.info(
                f"    -> {doc_result.change_count} changes, "
                f"{len(new_examples)} new learnings, "
                f"validation: {'PASS' if doc_result.validation_passed else 'FAIL'}, "
                f"glitches introduced: {len(doc_result.glitches_introduced)}"
            )
        elif doc_result.status == "error":
            chunk_result.failed += 1
        else:
            chunk_result.skipped += 1

        # Save individual result
        doc_result_path = results_dir / f"{doc_id}_result.json"
        doc_result_path.write_text(json.dumps(asdict(doc_result), indent=2, default=str))

    # Update accumulated examples with everything learned in this chunk
    accumulated_examples.extend(chunk_examples[len(accumulated_examples):])

    chunk_result.total_documents = len(docx_files)
    chunk_result.total_changes = len(all_changes)

    # Step 4: Aggregate analysis
    cat_counter: Counter = Counter()
    sev_counter: Counter = Counter()
    pattern_counter: Counter = Counter()

    for change in all_changes:
        cat_counter[change.get("category", "unknown")] += 1
        sev_counter[change.get("severity", "unknown")] += 1
        _classify_pattern(change.get("description", ""), pattern_counter)

    chunk_result.aggregate_by_category = dict(cat_counter)
    chunk_result.aggregate_by_severity = dict(sev_counter)
    chunk_result.common_patterns = dict(pattern_counter.most_common(15))

    # Step 5: Generate learnings from this chunk
    chunk_result.new_learnings = _extract_learnings(all_changes, chunk_number)

    # Step 6: Generate chunk-specific recommendations
    chunk_result.recommendations = _generate_chunk_recommendations(
        chunk_result, chunk_number
    )

    chunk_result.chunk_end_time = datetime.now().isoformat()
    chunk_result.chunk_duration_seconds = round(time.time() - chunk_start, 2)

    # Save chunk summary
    summary_path = chunk_dir / "chunk_summary.json"
    summary_path.write_text(json.dumps(asdict(chunk_result), indent=2, default=str))

    logger.info(f"  Chunk {chunk_number} complete: {chunk_result.successful} success, "
                f"{chunk_result.failed} failed, {chunk_result.total_changes} changes, "
                f"{len(chunk_result.new_learnings)} new learnings")

    return chunk_result


def _classify_pattern(description: str, counter: Counter) -> None:
    """Classify a change description into a named pattern."""
    desc = description.lower()
    patterns = [
        ("bold_mismatch", ["bold"]),
        ("font_mismatch", ["font", "calibri", "arial", "times"]),
        ("size_mismatch", ["size", "pt"]),
        ("underline_mismatch", ["underline"]),
        ("quote_issues", ["quote", "smart"]),
        ("alignment_mismatch", ["alignment", "justify", "left", "center"]),
        ("spacing_mismatch", ["spacing", "space before", "space after"]),
        ("cross_reference", ["reference", "section", "exhibit"]),
        ("duplicate_labels", ["duplicate"]),
        ("sequence_gap", ["sequence", "gap"]),
        ("definition_format", ["definition", "defined term"]),
        ("signature_block", ["signature"]),
        ("header_footer", ["header", "footer", "page number"]),
        ("numbering_format", ["numbering", "numid"]),
    ]
    for name, keywords in patterns:
        if any(kw in desc for kw in keywords):
            counter[name] += 1
            return
    counter["other"] += 1


def _extract_learnings(
    changes: list[dict], chunk_number: int
) -> list[dict]:
    """Extract new learning examples from a chunk's changes.

    Identifies repeated patterns that should be encoded as examples
    for future chunks.
    """
    learnings = []

    # Group changes by (category, rough pattern)
    groups: dict[str, list[dict]] = defaultdict(list)
    for change in changes:
        key = f"{change.get('category', 'other')}"
        groups[key].append(change)

    for key, group_changes in groups.items():
        if len(group_changes) >= 3:
            # This pattern appears frequently — worth learning from
            sample = group_changes[0]
            learnings.append({
                "category": sample.get("category", "other"),
                "description": f"Recurring pattern in chunk {chunk_number}: {sample.get('description', '')[:150]}",
                "frequency": len(group_changes),
                "sample_location": sample.get("location", ""),
                "chunk": chunk_number,
            })

    return learnings


def _generate_chunk_recommendations(
    chunk: ChunkResult, chunk_number: int
) -> list[str]:
    """Generate actionable recommendations from chunk results."""
    recs = []
    cats = chunk.aggregate_by_category
    patterns = chunk.common_patterns

    total = chunk.total_changes or 1  # Avoid division by zero

    # Font mismatches
    font_pct = (patterns.get("font_mismatch", 0) + patterns.get("size_mismatch", 0)) / total * 100
    if font_pct > 30:
        recs.append(
            f"Chunk {chunk_number}: {font_pct:.0f}% of changes are font/size mismatches. "
            f"Consider adding font family equivalence groups."
        )

    # Alignment
    align_pct = patterns.get("alignment_mismatch", 0) / total * 100
    if align_pct > 20:
        recs.append(
            f"Chunk {chunk_number}: {align_pct:.0f}% alignment mismatches. "
            f"Consider document-type-specific alignment defaults."
        )

    # Error rate
    if chunk.failed > chunk.total_documents * 0.3:
        recs.append(
            f"Chunk {chunk_number}: High failure rate ({chunk.failed}/{chunk.total_documents}). "
            f"Review error logs for common failure modes."
        )

    # Cross references
    if patterns.get("cross_reference", 0) > 5:
        recs.append(
            f"Chunk {chunk_number}: {patterns['cross_reference']} cross-reference issues. "
            f"Consider adding Word field code (REF, PAGEREF) analysis."
        )

    # Quote issues
    if patterns.get("quote_issues", 0) > 10:
        recs.append(
            f"Chunk {chunk_number}: {patterns['quote_issues']} quote issues. "
            f"The quote rule is catching these — verify fix quality."
        )

    # Other/unknown
    other_pct = patterns.get("other", 0) / total * 100
    if other_pct > 25:
        recs.append(
            f"Chunk {chunk_number}: {other_pct:.0f}% of issues are 'other' category. "
            f"These may represent new rule categories to implement."
        )

    if not recs:
        recs.append(f"Chunk {chunk_number}: Results look good — no major improvement areas identified.")

    return recs


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------


async def run_full_pipeline(
    num_chunks: int = 10,
    docs_per_chunk: int = 10,
    output_dir: Path | None = None,
) -> PipelineResult:
    """Run the full EDGAR self-test pipeline.

    Processes 100 documents in 10 chunks of 10, with recursive learning
    between chunks.

    Args:
        num_chunks: Number of chunks (default 10).
        docs_per_chunk: Documents per chunk (default 10).
        output_dir: Output directory for all artifacts.

    Returns:
        Complete PipelineResult with all data.
    """
    if output_dir is None:
        output_dir = settings.data_dir / "self_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline = PipelineResult(
        pipeline_id=f"selftest_{int(time.time())}",
        start_time=datetime.now().isoformat(),
        config={
            "num_chunks": num_chunks,
            "docs_per_chunk": docs_per_chunk,
            "total_target": num_chunks * docs_per_chunk,
        },
    )
    pipeline_start = time.time()

    logger.info(f"Starting EDGAR self-test pipeline: {num_chunks} chunks x {docs_per_chunk} docs")
    logger.info(f"Output directory: {output_dir}")

    # Accumulated examples grow across chunks (recursive learning)
    accumulated_examples: list[Example] = []

    # Divide search terms into chunks
    terms_per_chunk = max(3, len(CRE_SEARCH_TERMS) // num_chunks)

    for chunk_num in range(1, num_chunks + 1):
        # Select search terms for this chunk
        start_idx = (chunk_num - 1) * terms_per_chunk
        chunk_terms = CRE_SEARCH_TERMS[start_idx : start_idx + terms_per_chunk]
        if not chunk_terms:
            chunk_terms = CRE_SEARCH_TERMS[:3]  # Fallback

        # Process chunk
        chunk_result = await process_chunk(
            chunk_number=chunk_num,
            chunk_terms=chunk_terms,
            base_dir=output_dir,
            docs_per_chunk=docs_per_chunk,
            accumulated_examples=accumulated_examples,
        )
        pipeline.chunks.append(chunk_result)

        # Aggregate stats
        pipeline.total_documents += chunk_result.total_documents
        pipeline.total_successful += chunk_result.successful
        pipeline.total_failed += chunk_result.failed
        pipeline.total_skipped += chunk_result.skipped
        pipeline.total_changes += chunk_result.total_changes

        for cat, count in chunk_result.aggregate_by_category.items():
            pipeline.grand_by_category[cat] = pipeline.grand_by_category.get(cat, 0) + count
        for sev, count in chunk_result.aggregate_by_severity.items():
            pipeline.grand_by_severity[sev] = pipeline.grand_by_severity.get(sev, 0) + count

        # Recursive learning: convert chunk learnings to Examples
        for learning in chunk_result.new_learnings:
            example = Example(
                category=learning["category"],
                description=learning["description"],
                document_type="contract",
            )
            accumulated_examples.append(example)
            pipeline.cumulative_learnings.append(learning)

        # Track improvement trajectory
        pipeline.improvement_trajectory.append({
            "chunk": chunk_num,
            "cumulative_docs": pipeline.total_documents,
            "cumulative_changes": pipeline.total_changes,
            "cumulative_learnings": len(accumulated_examples),
            "changes_per_doc": round(
                pipeline.total_changes / max(pipeline.total_successful, 1), 1
            ),
            "success_rate": round(
                pipeline.total_successful / max(pipeline.total_documents, 1) * 100, 1
            ),
        })

        logger.info(f"\n--- Progress: {pipeline.total_documents} docs, "
                    f"{pipeline.total_changes} changes, "
                    f"{len(accumulated_examples)} learnings ---\n")

    # Final analysis
    pipeline.end_time = datetime.now().isoformat()
    pipeline.total_duration_seconds = round(time.time() - pipeline_start, 2)
    pipeline.final_recommendations = _generate_final_recommendations(pipeline)

    # Save final report
    report_path = output_dir / "pipeline_report.json"
    report_path.write_text(json.dumps(asdict(pipeline), indent=2, default=str))

    # Save human-readable summary
    _write_human_summary(pipeline, output_dir / "SUMMARY.md")

    logger.info(f"\n{'='*60}")
    logger.info(f"PIPELINE COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total documents: {pipeline.total_documents}")
    logger.info(f"Successful: {pipeline.total_successful}")
    logger.info(f"Failed: {pipeline.total_failed}")
    logger.info(f"Total changes: {pipeline.total_changes}")
    logger.info(f"Total learnings: {len(pipeline.cumulative_learnings)}")
    logger.info(f"Duration: {pipeline.total_duration_seconds:.0f}s")
    logger.info(f"Report: {report_path}")

    return pipeline


def _generate_final_recommendations(pipeline: PipelineResult) -> list[str]:
    """Generate final recommendations from the entire pipeline run."""
    recs = []

    # Aggregate all chunk recommendations
    all_chunk_recs = []
    for chunk in pipeline.chunks:
        all_chunk_recs.extend(chunk.recommendations)

    # Identify recurring themes
    theme_counts = Counter()
    for rec in all_chunk_recs:
        rec_lower = rec.lower()
        if "font" in rec_lower:
            theme_counts["font_handling"] += 1
        if "alignment" in rec_lower:
            theme_counts["alignment_defaults"] += 1
        if "reference" in rec_lower:
            theme_counts["cross_references"] += 1
        if "failure" in rec_lower or "error" in rec_lower:
            theme_counts["error_handling"] += 1
        if "other" in rec_lower or "new" in rec_lower:
            theme_counts["new_rules"] += 1

    if theme_counts.get("font_handling", 0) >= 3:
        recs.append(
            "PRIORITY: Font handling improvements needed. Add font family grouping "
            "(Times/Times New Roman, Arial/Helvetica) and size tolerance ranges."
        )

    if theme_counts.get("alignment_defaults", 0) >= 3:
        recs.append(
            "PRIORITY: Add document-type-specific alignment defaults. "
            "CRE contracts typically use JUSTIFY, briefs use LEFT."
        )

    if theme_counts.get("cross_references", 0) >= 3:
        recs.append(
            "PRIORITY: Enhance cross-reference detection to parse Word field codes "
            "(REF, PAGEREF) in addition to text-based references."
        )

    if theme_counts.get("error_handling", 0) >= 3:
        recs.append(
            "PRIORITY: Improve error resilience. Common failures include corrupt "
            "styles, missing numbering parts, and unexpected XML structures."
        )

    if theme_counts.get("new_rules", 0) >= 3:
        recs.append(
            "PRIORITY: Review 'other' category changes across all chunks. "
            "These likely represent new rule categories to implement."
        )

    # Improvement trajectory analysis
    trajectory = pipeline.improvement_trajectory
    if len(trajectory) >= 3:
        early_cpd = trajectory[0].get("changes_per_doc", 0)
        late_cpd = trajectory[-1].get("changes_per_doc", 0)
        if late_cpd < early_cpd * 0.8:
            recs.append(
                f"POSITIVE: Changes per document decreased from {early_cpd} to {late_cpd}, "
                f"suggesting the learning system is effectively reducing false positives."
            )
        elif late_cpd > early_cpd * 1.2:
            recs.append(
                f"NOTE: Changes per document increased from {early_cpd} to {late_cpd}. "
                f"The learning system may be introducing false positives — review examples."
            )

    if not recs:
        recs.append("The pipeline completed successfully with no major improvement areas identified.")

    return recs


def _write_human_summary(pipeline: PipelineResult, path: Path) -> None:
    """Write a human-readable markdown summary with glitch tracking sub-checklist."""
    # Collect all glitches across documents
    total_glitches_caught = 0
    total_glitches_introduced = 0
    validation_failures = 0
    header_issues = 0
    footer_issues = 0
    exhibit_issues = 0

    for chunk in pipeline.chunks:
        for doc in chunk.documents:
            total_glitches_caught += len(doc.glitches_caught)
            total_glitches_introduced += len(doc.glitches_introduced)
            if not doc.validation_passed:
                validation_failures += 1
            if not doc.headers_preserved:
                header_issues += 1
            if not doc.footers_preserved:
                footer_issues += 1
            if not doc.exhibits_preserved:
                exhibit_issues += 1

    lines = [
        "# EDGAR Self-Test Pipeline Results",
        "",
        f"**Run ID:** {pipeline.pipeline_id}",
        f"**Date:** {pipeline.start_time}",
        f"**Duration:** {pipeline.total_duration_seconds:.0f} seconds",
        "",
        "## Overview",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Documents processed | {pipeline.total_documents} |",
        f"| Successful | {pipeline.total_successful} |",
        f"| Failed | {pipeline.total_failed} |",
        f"| Skipped | {pipeline.total_skipped} |",
        f"| Total changes made | {pipeline.total_changes} |",
        f"| Learnings generated | {len(pipeline.cumulative_learnings)} |",
        "",
        "## Glitch Tracking Sub-Checklist",
        "",
        "### Formatting Glitches Caught (Good)",
        f"- [{'x' if total_glitches_caught > 0 else ' '}] Heading style mismatches detected: {sum(1 for c in pipeline.chunks for d in c.documents for g in d.glitches_caught if g.get('category') == 'heading_style')}",
        f"- [{'x' if total_glitches_caught > 0 else ' '}] Quote style issues detected: {sum(1 for c in pipeline.chunks for d in c.documents for g in d.glitches_caught if g.get('category') == 'quote_style')}",
        f"- [{'x' if total_glitches_caught > 0 else ' '}] List label issues detected: {sum(1 for c in pipeline.chunks for d in c.documents for g in d.glitches_caught if g.get('category') == 'list_labels')}",
        f"- [{'x' if total_glitches_caught > 0 else ' '}] Paragraph format issues detected: {sum(1 for c in pipeline.chunks for d in c.documents for g in d.glitches_caught if g.get('category') == 'paragraph_format')}",
        f"- [{'x' if total_glitches_caught > 0 else ' '}] Cross-reference issues detected: {sum(1 for c in pipeline.chunks for d in c.documents for g in d.glitches_caught if g.get('category') == 'cross_references')}",
        f"- [{'x' if total_glitches_caught > 0 else ' '}] Definition format issues detected: {sum(1 for c in pipeline.chunks for d in c.documents for g in d.glitches_caught if g.get('category') == 'definition_format')}",
        f"- [{'x' if total_glitches_caught > 0 else ' '}] Signature block issues detected: {sum(1 for c in pipeline.chunks for d in c.documents for g in d.glitches_caught if g.get('category') == 'signature_block')}",
        f"- [{'x' if total_glitches_caught > 0 else ' '}] Header/footer issues detected: {sum(1 for c in pipeline.chunks for d in c.documents for g in d.glitches_caught if g.get('category') == 'header_footer')}",
        f"- **Total glitches caught: {total_glitches_caught}**",
        "",
        "### Formatting Glitches Introduced (Bad — should be zero)",
        f"- [{'x' if total_glitches_introduced == 0 else ' '}] No new content loss: {pipeline.total_successful - sum(1 for c in pipeline.chunks for d in c.documents if not d.content_preserved)}/{pipeline.total_successful} docs OK",
        f"- [{'x' if header_issues == 0 else ' '}] No header corruption: {pipeline.total_successful - header_issues}/{pipeline.total_successful} docs OK",
        f"- [{'x' if footer_issues == 0 else ' '}] No footer corruption: {pipeline.total_successful - footer_issues}/{pipeline.total_successful} docs OK",
        f"- [{'x' if exhibit_issues == 0 else ' '}] No exhibit label corruption: {pipeline.total_successful - exhibit_issues}/{pipeline.total_successful} docs OK",
        f"- [{'x' if validation_failures == 0 else ' '}] All validation checks passed: {pipeline.total_successful - validation_failures}/{pipeline.total_successful} docs OK",
        f"- **Total glitches introduced: {total_glitches_introduced}**",
        "",
        "### Progressive Learning Verification",
    ]

    # Check if changes_per_doc decreased over time
    if len(pipeline.improvement_trajectory) >= 2:
        first = pipeline.improvement_trajectory[0]
        last = pipeline.improvement_trajectory[-1]
        improved = last.get("changes_per_doc", 0) <= first.get("changes_per_doc", 0)
        lines.append(f"- [{'x' if improved else ' '}] Changes per doc decreasing over time ({first.get('changes_per_doc')} -> {last.get('changes_per_doc')})")
        lines.append(f"- [x] Learnings accumulated: {last.get('cumulative_learnings', 0)}")
        lines.append(f"- [{'x' if last.get('success_rate', 0) > 50 else ' '}] Success rate: {last.get('success_rate', 0)}%")

    lines.extend([
        "",
        "## Changes by Category",
        "",
    ])

    for cat, count in sorted(pipeline.grand_by_category.items(), key=lambda x: -x[1]):
        lines.append(f"- **{cat}**: {count}")

    lines.extend([
        "",
        "## Changes by Severity",
        "",
    ])
    for sev, count in sorted(pipeline.grand_by_severity.items(), key=lambda x: -x[1]):
        lines.append(f"- **{sev}**: {count}")

    lines.extend([
        "",
        "## Improvement Trajectory",
        "",
        "| Chunk | Docs | Changes | Changes/Doc | Learnings | Success Rate |",
        "|-------|------|---------|-------------|-----------|-------------|",
    ])
    for t in pipeline.improvement_trajectory:
        lines.append(
            f"| {t['chunk']} | {t['cumulative_docs']} | "
            f"{t['cumulative_changes']} | {t['changes_per_doc']} | "
            f"{t['cumulative_learnings']} | {t['success_rate']}% |"
        )

    lines.extend([
        "",
        "## Chunk Summaries",
        "",
    ])
    for chunk in pipeline.chunks:
        lines.extend([
            f"### Chunk {chunk.chunk_number}",
            f"- Documents: {chunk.total_documents} ({chunk.successful} success, {chunk.failed} failed)",
            f"- Changes: {chunk.total_changes}",
            f"- Duration: {chunk.chunk_duration_seconds:.0f}s",
            f"- Search terms: {', '.join(chunk.search_terms_used[:3])}...",
        ])
        if chunk.recommendations:
            lines.append("- Recommendations:")
            for rec in chunk.recommendations:
                lines.append(f"  - {rec}")
        lines.append("")

    lines.extend([
        "## Final Recommendations",
        "",
    ])
    for i, rec in enumerate(pipeline.final_recommendations, 1):
        lines.append(f"{i}. {rec}")

    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def main():
    """CLI entry point for the EDGAR self-test pipeline."""
    import argparse

    parser = argparse.ArgumentParser(
        description="EDGAR Self-Test Pipeline — Process 100 legal documents through the polisher"
    )
    parser.add_argument(
        "--chunks", type=int, default=10,
        help="Number of chunks (default: 10)"
    )
    parser.add_argument(
        "--per-chunk", type=int, default=10,
        help="Documents per chunk (default: 10)"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output directory (default: data/self_test)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()
    output = Path(args.output) if args.output else None

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info(f"EDGAR Self-Test Pipeline: {args.chunks} chunks x {args.per_chunk} docs")
    result = asyncio.run(
        run_full_pipeline(
            num_chunks=args.chunks,
            docs_per_chunk=args.per_chunk,
            output_dir=output,
        )
    )
    logger.info(f"Done. Total: {result.total_documents} docs, {result.total_changes} changes")


if __name__ == "__main__":
    main()
