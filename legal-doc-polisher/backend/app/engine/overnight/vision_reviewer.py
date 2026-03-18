"""Vision Before/After Reviewer — the core of the overnight pipeline.

Sends ORIGINAL and POLISHED page images to Claude Vision side-by-side,
asking it to score the document against the 120-point formatting checklist.
Returns structured verdicts: PASS, FAIL, REGRESSION for each check item.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal

import anthropic

from ...config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Checklist Definition — 120 items across 11 categories
# ---------------------------------------------------------------------------

CHECKLIST_CATEGORIES = {
    "A": "Heading Consistency",
    "B": "Body Text Consistency",
    "C": "Quote & Punctuation",
    "D": "List & Numbering",
    "E": "Cross-Reference Integrity",
    "F": "Definition Formatting",
    "G": "Header & Footer",
    "H": "Signature Block",
    "I": "Exhibit & Schedule",
    "J": "Template Artifacts",
    "K": "Overall Visual Quality",
}

CHECKLIST_ITEMS = {
    "A1": "All Heading 1s use identical font family",
    "A2": "All Heading 1s use identical font size",
    "A3": "All Heading 1s have consistent bold/underline",
    "A4": "All Heading 2s use identical font family",
    "A5": "All Heading 2s use identical font size",
    "A6": "All Heading 2s have consistent bold/underline",
    "A7": "All Heading 3s use identical formatting",
    "A8": "Heading hierarchy is visually clear (H1 > H2 > H3)",
    "A9": "No heading uses a different font from document standard",
    "A10": "Section numbering format is consistent",
    "A11": "Article numbering is consistent (not mixed Roman/Arabic)",
    "A12": "Heading alignment is consistent within each level",
    "A13": "Space before headings is consistent",
    "A14": "Space after headings is consistent",
    "A15": "No orphan headings at bottom of page",
    "B1": "All body paragraphs use same font family",
    "B2": "All body paragraphs use same font size",
    "B3": "All body paragraphs have consistent alignment",
    "B4": "Line spacing is uniform across body",
    "B5": "Space before paragraphs is consistent",
    "B6": "Space after paragraphs is consistent",
    "B7": "First-line indentation is consistent",
    "B8": "No stray font color changes",
    "B9": "No accidental bold/italic in body",
    "B10": "No mixed font sizes within a paragraph",
    "B11": "Text is not cut off at margins",
    "B12": "No rivers of white space in justified text",
    "B13": "No orphan lines at top of page",
    "B14": "No widow lines at bottom of page",
    "B15": "Paragraph spacing doesn't vary between sections",
    "C1": "All double quotes are smart (curly) quotes",
    "C2": "All single quotes/apostrophes are smart",
    "C3": "No straight quotes remain",
    "C4": "Opening quotes face correct direction",
    "C5": "Closing quotes face correct direction",
    "C6": "Apostrophes in contractions use right single quote",
    "C7": "Em dashes are consistent",
    "C8": "En dashes are consistent in ranges",
    "C9": "Ellipses are consistent",
    "C10": "No double punctuation",
    "C11": "Period/semicolon consistency in enumerated lists",
    "C12": "Oxford comma usage is consistent",
    "D1": "No duplicate list labels",
    "D2": "No gaps in list numbering sequences",
    "D3": "List label format is consistent within each list",
    "D4": "Nested list indentation increases properly",
    "D5": "List labels align vertically",
    "D6": "Hanging indent is consistent across lists",
    "D7": "Bullet style is consistent",
    "D8": "Numbered list restarts are intentional",
    "D9": "Sub-list format is consistent",
    "D10": "List item text alignment is consistent",
    "D11": "No phantom numbering",
    "D12": "Terminal punctuation in list items is consistent",
    "E1": "All Section references point to existing sections",
    "E2": "All Article references point to existing articles",
    "E3": "All Exhibit references match existing labels",
    "E4": "Section reference format is consistent",
    "E5": "No stale references to renamed sections",
    "E6": "Parenthetical descriptions match section titles",
    "E7": "Directional references (above/below) are correct",
    "E8": "No self-referential sections",
    "E9": "Schedule/Appendix references match labels",
    "E10": "Page number references are correct",
    "F1": "Defined terms use consistent formatting",
    "F2": "All used defined terms are actually defined",
    "F3": "Definitions are in alphabetical order",
    "F4": "Definition phrasing is consistent (means vs shall mean)",
    "F5": "No duplicate definitions",
    "F6": "Defined terms maintain formatting in body",
    "F7": "No circular definitions",
    "F8": "Terminal punctuation in definitions is consistent",
    "F9": "Nested quotes in definitions are differentiated",
    "F10": "Capitalization of defined terms is consistent",
    "G1": "Header font is consistent across pages",
    "G2": "Header content is consistent",
    "G3": "Footer font is consistent across pages",
    "G4": "Page numbering format is consistent",
    "G5": "Page numbers are sequential",
    "G6": "No DRAFT watermark on final document",
    "G7": "Confidentiality labels are consistent",
    "G8": "No stale dates in headers/footers",
    "G9": "Party names in headers match body",
    "G10": "Header/footer margins are consistent",
    "H1": "All signature blocks use same structure",
    "H2": "By/Name/Title/Date fields are consistent",
    "H3": "Signature line formatting is consistent",
    "H4": "Alignment of signature blocks is consistent",
    "H5": "Entity names match preamble exactly",
    "H6": "Entity type matches throughout",
    "H7": "All required parties have signature blocks",
    "H8": "No duplicate signature blocks",
    "H9": "Date lines use consistent format",
    "H10": "Spacing within signature blocks is uniform",
    "I1": "Exhibit labels are sequential",
    "I2": "Exhibit title formatting is consistent",
    "I3": "Exhibit headers reference parent document",
    "I4": "No placeholder text in exhibits",
    "I5": "Multi-page exhibits have continuation headers",
    "I6": "Exhibit page numbering is consistent",
    "I7": "Legal descriptions use consistent formatting",
    "I8": "Exhibit fonts match main document",
    "I9": "Schedule formatting matches exhibit formatting",
    "I10": "Attachment/addendum labels are consistent",
    "J1": "No placeholder text remains",
    "J2": "No conflicting governing law clauses",
    "J3": "No duplicate boilerplate sections",
    "J4": "No wrong party-type language",
    "J5": "No conditional/instructional text",
    "J6": "Property address is consistent throughout",
    "J7": "No tracked changes artifacts",
    "J8": "No hidden comments remaining",
    "K1": "Document looks professionally formatted",
    "K2": "No jarring transitions between sections",
    "K3": "Consistent visual weight across document",
    "K4": "Tables have consistent formatting",
    "K5": "No awkward page breaks mid-sentence",
    "K6": "Margins are consistent throughout",
    "K7": "No visible formatting artifacts",
    "K8": "Overall document is visually cohesive",
}


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class CheckItemResult:
    """Result for a single checklist item."""

    item_id: str
    description: str
    verdict: Literal["pass", "fail", "regression", "not_applicable", "unknown"] = "unknown"
    details: str = ""
    severity: Literal["minor", "moderate", "major", "critical"] = "minor"
    fixable: bool = False
    fix_suggestion: str = ""


@dataclass
class PageReviewResult:
    """Vision review result for a single page comparison."""

    page_number: int
    items_checked: list[CheckItemResult] = field(default_factory=list)
    overall_improved: bool = True
    issues_found: int = 0
    regressions_found: int = 0


@dataclass
class DocumentReviewResult:
    """Complete vision review result for a document."""

    document_id: str
    filename: str
    page_reviews: list[PageReviewResult] = field(default_factory=list)
    total_checks: int = 0
    total_pass: int = 0
    total_fail: int = 0
    total_regression: int = 0
    total_na: int = 0
    pass_rate: float = 0.0
    improvement_score: float = 0.0
    actionable_fixes: list[dict] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Vision Review Engine
# ---------------------------------------------------------------------------


async def review_before_after(
    original_images: list[Path],
    polished_images: list[Path],
    document_id: str,
    filename: str,
    focus_categories: list[str] | None = None,
) -> DocumentReviewResult:
    """Send before/after page images to Claude Vision for 120-point review.

    Args:
        original_images: Paths to original document page PNGs.
        polished_images: Paths to polished document page PNGs.
        document_id: Unique identifier.
        filename: Original filename.
        focus_categories: Optional category filter (e.g., ["A", "B", "C"]).

    Returns:
        DocumentReviewResult with all checklist verdicts.
    """
    result = DocumentReviewResult(document_id=document_id, filename=filename)

    if not settings.anthropic_api_key:
        logger.warning("No API key — returning empty review")
        return result

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Review pages in pairs (original + polished)
    num_pages = min(len(original_images), len(polished_images))
    pages_to_review = min(num_pages, 20)  # Cap at 20 pages per document

    # Determine which checklist categories to focus on per page
    # First/last pages get header/footer/signature checks
    # All pages get heading/body/quote/list checks

    for page_idx in range(pages_to_review):
        page_num = page_idx + 1
        is_first_page = page_idx == 0
        is_last_pages = page_idx >= pages_to_review - 3

        # Select relevant categories for this page
        categories = ["A", "B", "C", "D", "K"]  # Always check these
        if is_first_page:
            categories.extend(["G", "J"])
        if is_last_pages:
            categories.extend(["H", "I"])
        if page_idx < 5:
            categories.extend(["E", "F"])

        if focus_categories:
            categories = [c for c in categories if c in focus_categories]
        categories = list(set(categories))

        try:
            page_review = await _review_page_pair(
                client=client,
                original_image=original_images[page_idx],
                polished_image=polished_images[page_idx],
                page_number=page_num,
                total_pages=pages_to_review,
                categories=categories,
            )
            result.page_reviews.append(page_review)
        except Exception as e:
            logger.warning(f"  Vision review failed for page {page_num}: {e}")

    # Aggregate results
    _aggregate_results(result)
    return result


async def _review_page_pair(
    client: anthropic.Anthropic,
    original_image: Path,
    polished_image: Path,
    page_number: int,
    total_pages: int,
    categories: list[str],
) -> PageReviewResult:
    """Review a single page pair (original vs polished) with Vision."""
    # Read and encode both images
    orig_b64 = base64.standard_b64encode(original_image.read_bytes()).decode()
    pol_b64 = base64.standard_b64encode(polished_image.read_bytes()).decode()

    # Build the checklist subset for this page
    items_to_check = {
        k: v for k, v in CHECKLIST_ITEMS.items()
        if k[0] in categories
    }

    checklist_text = "\n".join(f"- {k}: {v}" for k, v in items_to_check.items())

    prompt = f"""You are a legal document formatting quality auditor.

I'm showing you two versions of page {page_number} of {total_pages} from a legal document:
- IMAGE 1 (LEFT): The ORIGINAL document (before polishing)
- IMAGE 2 (RIGHT): The POLISHED document (after automated formatting fixes)

Review the POLISHED version against this checklist. For each item, determine:
- "pass" = The polished version correctly handles this (either it was already correct, or it was fixed)
- "fail" = The polished version still has this problem (the fix didn't work or wasn't attempted)
- "regression" = The polished version INTRODUCED this problem (it was fine in original, broken now)
- "not_applicable" = This check doesn't apply to this page

CHECKLIST ITEMS TO REVIEW:
{checklist_text}

Return a JSON array with one entry per checklist item:
```json
[
  {{
    "item_id": "A1",
    "verdict": "pass|fail|regression|not_applicable",
    "details": "Brief explanation of what you see",
    "severity": "minor|moderate|major|critical",
    "fixable": true/false,
    "fix_suggestion": "What code change would fix this (if fixable)"
  }}
]
```

Be thorough and precise. Pay special attention to REGRESSIONS — it is critical that
the polisher does not make things worse. If unsure, lean toward "fail" rather than "pass".
Only mark "pass" when you are confident the formatting is correct."""

    message = client.messages.create(
        model=settings.vision_model,
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": orig_b64},
                    },
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": pol_b64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    # Parse response
    response_text = "".join(
        block.text for block in message.content if hasattr(block, "text")
    )

    items = _parse_review_response(response_text, items_to_check)

    page_result = PageReviewResult(page_number=page_number)
    page_result.items_checked = items
    page_result.issues_found = sum(1 for i in items if i.verdict == "fail")
    page_result.regressions_found = sum(1 for i in items if i.verdict == "regression")
    page_result.overall_improved = page_result.regressions_found == 0

    return page_result


def _parse_review_response(
    response_text: str, expected_items: dict[str, str]
) -> list[CheckItemResult]:
    """Parse Claude's review response into CheckItemResult objects."""
    results = []

    # Try JSON extraction
    json_data = None
    try:
        # Find JSON array in response
        match = re.search(r"\[[\s\S]*\]", response_text)
        if match:
            json_data = json.loads(match.group(0))
    except json.JSONDecodeError:
        pass

    if json_data and isinstance(json_data, list):
        for item in json_data:
            if not isinstance(item, dict):
                continue
            item_id = item.get("item_id", "")
            if item_id not in expected_items:
                continue
            results.append(CheckItemResult(
                item_id=item_id,
                description=expected_items.get(item_id, ""),
                verdict=item.get("verdict", "unknown"),
                details=item.get("details", ""),
                severity=item.get("severity", "minor"),
                fixable=item.get("fixable", False),
                fix_suggestion=item.get("fix_suggestion", ""),
            ))

    # Fill in any items not returned by the API
    returned_ids = {r.item_id for r in results}
    for item_id, desc in expected_items.items():
        if item_id not in returned_ids:
            results.append(CheckItemResult(
                item_id=item_id,
                description=desc,
                verdict="unknown",
            ))

    return results


def _aggregate_results(result: DocumentReviewResult) -> None:
    """Aggregate page-level results into document-level stats."""
    all_items: dict[str, CheckItemResult] = {}

    # Merge results across pages (worst verdict wins for each item)
    for page in result.page_reviews:
        for item in page.items_checked:
            if item.item_id not in all_items:
                all_items[item.item_id] = item
            else:
                existing = all_items[item.item_id]
                # regression > fail > unknown > pass > not_applicable
                priority = {"regression": 5, "fail": 4, "unknown": 3, "pass": 2, "not_applicable": 1}
                if priority.get(item.verdict, 0) > priority.get(existing.verdict, 0):
                    all_items[item.item_id] = item

    result.total_checks = len(all_items)
    result.total_pass = sum(1 for i in all_items.values() if i.verdict == "pass")
    result.total_fail = sum(1 for i in all_items.values() if i.verdict == "fail")
    result.total_regression = sum(1 for i in all_items.values() if i.verdict == "regression")
    result.total_na = sum(1 for i in all_items.values() if i.verdict == "not_applicable")

    applicable = result.total_checks - result.total_na
    result.pass_rate = (result.total_pass / max(applicable, 1)) * 100

    # Improvement score: passes minus regressions, normalized
    result.improvement_score = (
        (result.total_pass - result.total_regression * 3) / max(applicable, 1) * 100
    )

    # Collect actionable fixes
    result.actionable_fixes = [
        {
            "item_id": item.item_id,
            "description": item.description,
            "verdict": item.verdict,
            "severity": item.severity,
            "fix_suggestion": item.fix_suggestion,
            "details": item.details,
        }
        for item in all_items.values()
        if item.verdict in ("fail", "regression") and item.fixable
    ]

    result.summary = (
        f"Checked {result.total_checks} items: "
        f"{result.total_pass} pass, {result.total_fail} fail, "
        f"{result.total_regression} regression, {result.total_na} N/A. "
        f"Pass rate: {result.pass_rate:.1f}%. "
        f"Improvement score: {result.improvement_score:.1f}%."
    )
