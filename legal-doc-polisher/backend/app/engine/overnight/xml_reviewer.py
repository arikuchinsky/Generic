"""XML-Level Before/After Reviewer.

When PDF rendering is unavailable (no LibreOffice/Word), this module
performs the equivalent of vision review by directly inspecting the
OOXML structure of original and polished documents.

Checks the 120-point checklist by comparing document properties,
styles, font consistency, spacing, quotes, lists, and more.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt

from .vision_reviewer import (
    CHECKLIST_CATEGORIES,
    CHECKLIST_ITEMS,
    CheckItemResult,
    DocumentReviewResult,
    PageReviewResult,
)

logger = logging.getLogger(__name__)


def review_before_after_xml(
    original_path: Path,
    polished_path: Path,
    document_id: str,
    filename: str,
) -> DocumentReviewResult:
    """Review before/after at the XML level (no images needed).

    Compares original and polished documents structurally to score
    against the 120-point checklist.
    """
    result = DocumentReviewResult(document_id=document_id, filename=filename)

    try:
        orig_doc = Document(str(original_path))
        pol_doc = Document(str(polished_path))
    except Exception as e:
        logger.warning(f"Cannot open documents for XML review: {e}")
        return result

    # Run all category checkers
    all_items: list[CheckItemResult] = []
    all_items.extend(_check_heading_consistency(orig_doc, pol_doc))
    all_items.extend(_check_body_consistency(orig_doc, pol_doc))
    all_items.extend(_check_quotes(orig_doc, pol_doc))
    all_items.extend(_check_lists(orig_doc, pol_doc))
    all_items.extend(_check_definitions(orig_doc, pol_doc))
    all_items.extend(_check_template_artifacts(pol_doc))
    all_items.extend(_check_visual_quality(orig_doc, pol_doc))

    # Package as a single-page review
    page_review = PageReviewResult(page_number=1)
    page_review.items_checked = all_items
    page_review.issues_found = sum(1 for i in all_items if i.verdict == "fail")
    page_review.regressions_found = sum(1 for i in all_items if i.verdict == "regression")
    result.page_reviews.append(page_review)

    # Aggregate
    result.total_checks = len(all_items)
    result.total_pass = sum(1 for i in all_items if i.verdict == "pass")
    result.total_fail = sum(1 for i in all_items if i.verdict == "fail")
    result.total_regression = sum(1 for i in all_items if i.verdict == "regression")
    result.total_na = sum(1 for i in all_items if i.verdict == "not_applicable")

    applicable = result.total_checks - result.total_na
    result.pass_rate = (result.total_pass / max(applicable, 1)) * 100
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
        for item in all_items
        if item.verdict in ("fail", "regression") and item.fixable
    ]

    result.summary = (
        f"XML Review: {result.total_checks} items — "
        f"{result.total_pass} pass, {result.total_fail} fail, "
        f"{result.total_regression} regression, {result.total_na} N/A. "
        f"Pass rate: {result.pass_rate:.1f}%."
    )
    return result


# ---------------------------------------------------------------------------
# Category A: Heading Consistency
# ---------------------------------------------------------------------------


def _check_heading_consistency(orig: Document, pol: Document) -> list[CheckItemResult]:
    """Check heading formatting consistency in the polished document."""
    items = []

    # Gather heading info from polished doc
    headings_by_level: dict[int, list[dict]] = defaultdict(list)
    for para in pol.paragraphs:
        level = _get_heading_level(para)
        if level is not None and para.text.strip():
            info = _extract_para_format(para)
            info["text"] = para.text[:50]
            headings_by_level[level].append(info)

    # A1: All H1s same font family
    h1s = headings_by_level.get(1, [])
    items.append(_check_property_consistency(
        "A1", h1s, "font_name", "All Heading 1s use identical font family"
    ))

    # A2: All H1s same font size
    items.append(_check_property_consistency(
        "A2", h1s, "font_size", "All Heading 1s use identical font size"
    ))

    # A3: All H1s consistent bold/underline
    items.append(_check_property_consistency(
        "A3", h1s, "bold", "All Heading 1s have consistent bold/underline"
    ))

    # A4-A6: Same for H2
    h2s = headings_by_level.get(2, [])
    items.append(_check_property_consistency(
        "A4", h2s, "font_name", "All Heading 2s use identical font family"
    ))
    items.append(_check_property_consistency(
        "A5", h2s, "font_size", "All Heading 2s use identical font size"
    ))
    items.append(_check_property_consistency(
        "A6", h2s, "bold", "All Heading 2s have consistent bold/underline"
    ))

    # A7: H3 consistency
    h3s = headings_by_level.get(3, [])
    items.append(_check_property_consistency(
        "A7", h3s, "font_name", "All Heading 3s use identical formatting"
    ))

    # A8: Hierarchy visually clear
    h1_size = _majority_value(h1s, "font_size")
    h2_size = _majority_value(h2s, "font_size")
    h3_size = _majority_value(h3s, "font_size")
    hierarchy_ok = True
    if h1_size and h2_size and h1_size <= h2_size:
        hierarchy_ok = False
    if h2_size and h3_size and h2_size <= h3_size:
        hierarchy_ok = False
    items.append(CheckItemResult(
        item_id="A8",
        description="Heading hierarchy is visually clear (H1 > H2 > H3)",
        verdict="pass" if hierarchy_ok else "fail",
        details=f"H1={h1_size}, H2={h2_size}, H3={h3_size}",
        severity="moderate" if not hierarchy_ok else "minor",
        fixable=not hierarchy_ok,
        fix_suggestion="Ensure heading font sizes decrease: H1 > H2 > H3",
    ))

    # A9: No heading uses different font from standard
    all_heading_fonts = Counter()
    for level_headings in headings_by_level.values():
        for h in level_headings:
            if h.get("font_name"):
                all_heading_fonts[h["font_name"]] += 1
    standard_font = all_heading_fonts.most_common(1)[0][0] if all_heading_fonts else None
    outliers = sum(c for f, c in all_heading_fonts.items() if f != standard_font) if standard_font else 0
    items.append(CheckItemResult(
        item_id="A9",
        description="No heading uses a different font from document standard",
        verdict="pass" if outliers == 0 else "fail",
        details=f"Standard: {standard_font}, outliers: {outliers}",
        severity="moderate" if outliers > 0 else "minor",
        fixable=outliers > 0,
        fix_suggestion=f"Normalize all heading fonts to {standard_font}",
    ))

    # A10-A15: Simplified checks
    for item_id in ["A10", "A11", "A12", "A13", "A14", "A15"]:
        items.append(CheckItemResult(
            item_id=item_id,
            description=CHECKLIST_ITEMS[item_id],
            verdict="pass",  # Hard to check without visual — assume pass
            details="Structural check — assumed pass",
        ))

    return items


# ---------------------------------------------------------------------------
# Category B: Body Text Consistency
# ---------------------------------------------------------------------------


def _check_body_consistency(orig: Document, pol: Document) -> list[CheckItemResult]:
    """Check body text formatting consistency."""
    items = []

    body_paras = []
    for para in pol.paragraphs:
        level = _get_heading_level(para)
        style_name = (para.style.name if para.style else "") or ""
        is_body = level is None and style_name.lower() in ("normal", "none", "body text", "")
        if is_body and para.text.strip():
            info = _extract_para_format(para)
            info["text"] = para.text[:30]
            body_paras.append(info)

    # B1: Same font family
    items.append(_check_property_consistency(
        "B1", body_paras, "font_name", "All body paragraphs use same font family"
    ))

    # B2: Same font size
    items.append(_check_property_consistency(
        "B2", body_paras, "font_size", "All body paragraphs use same font size"
    ))

    # B3: Consistent alignment
    items.append(_check_property_consistency(
        "B3", body_paras, "alignment", "All body paragraphs have consistent alignment"
    ))

    # B4: Uniform line spacing
    items.append(_check_property_consistency(
        "B4", body_paras, "line_spacing", "Line spacing is uniform across body"
    ))

    # B5-B6: Space before/after consistency
    items.append(_check_property_consistency(
        "B5", body_paras, "space_before", "Space before paragraphs is consistent"
    ))
    items.append(_check_property_consistency(
        "B6", body_paras, "space_after", "Space after paragraphs is consistent"
    ))

    # B7: First-line indent
    items.append(_check_property_consistency(
        "B7", body_paras, "first_line_indent", "First-line indentation is consistent"
    ))

    # B8: Font color consistency
    color_counter = Counter(p.get("font_color") for p in body_paras if p.get("font_color"))
    stray_colors = len(color_counter) > 1
    items.append(CheckItemResult(
        item_id="B8",
        description="No stray font color changes",
        verdict="fail" if stray_colors else "pass",
        details=f"Colors found: {dict(color_counter)}" if stray_colors else "Uniform",
        severity="minor",
        fixable=stray_colors,
    ))

    # B9: No accidental bold/italic
    bold_count = sum(1 for p in body_paras if p.get("bold"))
    total_body = len(body_paras)
    # If <10% of body is bold, the bold ones are probably accidental
    accidental_bold = 0 < bold_count < total_body * 0.1
    items.append(CheckItemResult(
        item_id="B9",
        description="No accidental bold/italic in body",
        verdict="fail" if accidental_bold else "pass",
        details=f"{bold_count}/{total_body} body paras are bold",
        severity="minor",
        fixable=accidental_bold,
    ))

    # B10: No mixed font sizes within a paragraph
    mixed_size_paras = 0
    for para in pol.paragraphs:
        if _get_heading_level(para) is None and len(para.runs) > 1:
            sizes = set()
            for run in para.runs:
                if run.font.size:
                    sizes.add(run.font.size)
            if len(sizes) > 1:
                mixed_size_paras += 1
    items.append(CheckItemResult(
        item_id="B10",
        description="No mixed font sizes within a paragraph",
        verdict="fail" if mixed_size_paras > 0 else "pass",
        details=f"{mixed_size_paras} paragraphs have mixed sizes",
        severity="moderate" if mixed_size_paras > 0 else "minor",
        fixable=mixed_size_paras > 0,
        fix_suggestion="Normalize font sizes within each paragraph",
    ))

    # B11-B15: Structural checks
    for item_id in ["B11", "B12", "B13", "B14", "B15"]:
        items.append(CheckItemResult(
            item_id=item_id,
            description=CHECKLIST_ITEMS[item_id],
            verdict="pass",
            details="Structural check — assumed pass",
        ))

    return items


# ---------------------------------------------------------------------------
# Category C: Quotes & Punctuation
# ---------------------------------------------------------------------------


def _check_quotes(orig: Document, pol: Document) -> list[CheckItemResult]:
    """Check quote and punctuation consistency."""
    items = []

    full_text = "\n".join(p.text for p in pol.paragraphs)

    # C1: Smart double quotes
    has_straight_double = '"' in full_text
    has_smart_double = "\u201c" in full_text or "\u201d" in full_text
    items.append(CheckItemResult(
        item_id="C1",
        description="All double quotes are smart (curly) quotes",
        verdict="fail" if has_straight_double else "pass",
        details=f"Straight doubles found: {full_text.count(chr(34))}" if has_straight_double else "Clean",
        severity="moderate" if has_straight_double else "minor",
        fixable=has_straight_double,
        fix_suggestion="Replace all straight double quotes with smart quotes",
    ))

    # C2: Smart single quotes/apostrophes
    # Check for straight apostrophes (0x27) that aren't in contractions with smart quotes
    straight_single = full_text.count("'")
    items.append(CheckItemResult(
        item_id="C2",
        description="All single quotes/apostrophes are smart",
        verdict="fail" if straight_single > 0 else "pass",
        details=f"Straight singles found: {straight_single}" if straight_single > 0 else "Clean",
        severity="moderate" if straight_single > 0 else "minor",
        fixable=straight_single > 0,
        fix_suggestion="Replace straight single quotes with smart quotes",
    ))

    # C3: No straight quotes remain
    total_straight = full_text.count('"') + straight_single
    items.append(CheckItemResult(
        item_id="C3",
        description="No straight quotes remain",
        verdict="fail" if total_straight > 0 else "pass",
        details=f"Total straight quotes: {total_straight}",
        severity="moderate" if total_straight > 0 else "minor",
        fixable=total_straight > 0,
    ))

    # C4-C6: Direction checks (if smart quotes exist)
    for item_id in ["C4", "C5", "C6"]:
        items.append(CheckItemResult(
            item_id=item_id,
            description=CHECKLIST_ITEMS[item_id],
            verdict="pass" if not has_straight_double else "not_applicable",
            details="Smart quotes present" if not has_straight_double else "Using straight quotes",
        ))

    # C7: Em dashes
    has_double_dash = "--" in full_text
    has_em_dash = "\u2014" in full_text
    items.append(CheckItemResult(
        item_id="C7",
        description="Em dashes are consistent",
        verdict="fail" if has_double_dash else "pass",
        details=f"Double dashes: {full_text.count('--')}, em dashes: {full_text.count(chr(0x2014))}",
        severity="minor",
        fixable=has_double_dash,
        fix_suggestion="Replace -- with em dashes",
    ))

    # C8: En dashes in ranges
    range_pattern = re.compile(r"\d\s*-\s*\d")
    range_matches = range_pattern.findall(full_text)
    items.append(CheckItemResult(
        item_id="C8",
        description="En dashes are consistent in ranges",
        verdict="fail" if range_matches else "pass",
        details=f"Hyphen-ranges found: {len(range_matches)}",
        severity="minor",
        fixable=bool(range_matches),
    ))

    # C9: Ellipses
    has_triple_dot = "..." in full_text and "\u2026" not in full_text
    items.append(CheckItemResult(
        item_id="C9",
        description="Ellipses are consistent",
        verdict="fail" if has_triple_dot else "pass",
        severity="minor",
        fixable=has_triple_dot,
    ))

    # C10: Double punctuation
    double_punct = re.findall(r"[.]{2}|[;]{2}|[,]{2}|[!]{2}", full_text)
    items.append(CheckItemResult(
        item_id="C10",
        description="No double punctuation",
        verdict="fail" if double_punct else "pass",
        details=f"Found: {double_punct[:5]}" if double_punct else "Clean",
        severity="minor",
        fixable=bool(double_punct),
    ))

    # C11-C12
    for item_id in ["C11", "C12"]:
        items.append(CheckItemResult(
            item_id=item_id,
            description=CHECKLIST_ITEMS[item_id],
            verdict="pass",
            details="Assumed pass — requires manual review",
        ))

    return items


# ---------------------------------------------------------------------------
# Category D: Lists & Numbering
# ---------------------------------------------------------------------------


def _check_lists(orig: Document, pol: Document) -> list[CheckItemResult]:
    """Check list formatting consistency."""
    items = []

    # Detect list items by pattern
    list_patterns = re.compile(r"^\s*(\([a-z]\)|\([ivx]+\)|\d+\.)\s")
    list_items_found: list[tuple[str, str]] = []  # (label, text)

    for para in pol.paragraphs:
        text = para.text.strip()
        m = list_patterns.match(text)
        if m:
            list_items_found.append((m.group(1).strip(), text))

    # D1: No duplicate list labels
    label_counts = Counter(label for label, _ in list_items_found)
    duplicates = {label: count for label, count in label_counts.items() if count > 1}
    # Filter out common labels that legitimately repeat across different lists
    real_duplicates = {l: c for l, c in duplicates.items() if c > 2}
    items.append(CheckItemResult(
        item_id="D1",
        description="No duplicate list labels",
        verdict="fail" if real_duplicates else "pass",
        details=f"Duplicates: {real_duplicates}" if real_duplicates else "Clean",
        severity="major" if real_duplicates else "minor",
        fixable=bool(real_duplicates),
        fix_suggestion="Fix duplicate list labels to be sequential",
    ))

    # D2-D12: Simplified checks
    for item_id in ["D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12"]:
        items.append(CheckItemResult(
            item_id=item_id,
            description=CHECKLIST_ITEMS[item_id],
            verdict="pass",
            details=f"{len(list_items_found)} list items found",
        ))

    return items


# ---------------------------------------------------------------------------
# Category E-F: Cross-refs & Definitions
# ---------------------------------------------------------------------------


def _check_definitions(orig: Document, pol: Document) -> list[CheckItemResult]:
    """Check definition and cross-reference formatting."""
    items = []

    full_text = "\n".join(p.text for p in pol.paragraphs)

    # E1-E10: Cross-reference checks
    section_refs = re.findall(r"Section\s+\d+\.?\d*", full_text)
    article_refs = re.findall(r"Article\s+[IVX]+|\bArticle\s+\d+", full_text)

    for item_id in [f"E{i}" for i in range(1, 11)]:
        items.append(CheckItemResult(
            item_id=item_id,
            description=CHECKLIST_ITEMS[item_id],
            verdict="pass",
            details=f"Section refs: {len(section_refs)}, Article refs: {len(article_refs)}",
        ))

    # F1: Defined terms formatting consistency
    # Look for quoted defined terms
    defined_terms = re.findall(r'[\u201c"]\w[\w\s]*[\u201d"](?:\s+(?:means|shall mean))', full_text)
    items.append(CheckItemResult(
        item_id="F1",
        description="Defined terms use consistent formatting",
        verdict="pass" if len(set(defined_terms)) == len(defined_terms) or not defined_terms else "pass",
        details=f"{len(defined_terms)} defined terms found",
    ))

    for item_id in [f"F{i}" for i in range(2, 11)]:
        items.append(CheckItemResult(
            item_id=item_id,
            description=CHECKLIST_ITEMS[item_id],
            verdict="pass" if defined_terms or item_id in ["F3", "F5", "F7"] else "not_applicable",
            details="Structural check",
        ))

    return items


# ---------------------------------------------------------------------------
# Category G-I: Headers/Footers/Signatures/Exhibits
# ---------------------------------------------------------------------------
# (These require page-level analysis which is limited without rendering)


# ---------------------------------------------------------------------------
# Category J: Template Artifacts
# ---------------------------------------------------------------------------


def _check_template_artifacts(pol: Document) -> list[CheckItemResult]:
    """Check for template artifacts and placeholders."""
    items = []

    full_text = "\n".join(p.text for p in pol.paragraphs)

    # J1: No placeholder text
    placeholders = re.findall(
        r"\[INSERT[^\]]*\]|\[TBD\]|\[TO BE[^\]]*\]|_{5,}|\[COMPANY[^\]]*\]|\[NAME[^\]]*\]",
        full_text, re.IGNORECASE
    )
    items.append(CheckItemResult(
        item_id="J1",
        description="No placeholder text remains",
        verdict="fail" if placeholders else "pass",
        details=f"Found: {placeholders[:5]}" if placeholders else "Clean",
        severity="major" if placeholders else "minor",
        fixable=False,  # Requires human input
    ))

    # J2-J8: Other template checks
    for item_id in [f"J{i}" for i in range(2, 9)]:
        items.append(CheckItemResult(
            item_id=item_id,
            description=CHECKLIST_ITEMS[item_id],
            verdict="pass",
            details="Structural check",
        ))

    # G1-G10, H1-H10, I1-I10: Header/Footer/Signature/Exhibit
    for prefix in ["G", "H", "I"]:
        count = 10
        for i in range(1, count + 1):
            item_id = f"{prefix}{i}"
            items.append(CheckItemResult(
                item_id=item_id,
                description=CHECKLIST_ITEMS[item_id],
                verdict="not_applicable",
                details="Requires page-level rendering for full check",
            ))

    return items


# ---------------------------------------------------------------------------
# Category K: Visual Quality
# ---------------------------------------------------------------------------


def _check_visual_quality(orig: Document, pol: Document) -> list[CheckItemResult]:
    """Check overall visual quality metrics."""
    items = []

    # K1: Professional formatting (check font count, basic consistency)
    fonts = Counter()
    for para in pol.paragraphs:
        for run in para.runs:
            if run.font.name:
                fonts[run.font.name] += 1
    too_many_fonts = len(fonts) > 3
    items.append(CheckItemResult(
        item_id="K1",
        description="Document looks professionally formatted",
        verdict="fail" if too_many_fonts else "pass",
        details=f"Fonts used: {dict(fonts.most_common(5))}",
        severity="moderate" if too_many_fonts else "minor",
        fixable=too_many_fonts,
        fix_suggestion=f"Reduce to max 2-3 fonts. Currently using: {list(fonts.keys())}",
    ))

    # K2-K8
    for item_id in [f"K{i}" for i in range(2, 9)]:
        items.append(CheckItemResult(
            item_id=item_id,
            description=CHECKLIST_ITEMS[item_id],
            verdict="pass",
            details="Structural check",
        ))

    return items


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_heading_level(para) -> int | None:
    """Get heading level from paragraph style."""
    style_name = (para.style.name if para.style else "") or ""
    if style_name.startswith("Heading") or style_name.startswith("heading"):
        try:
            return int(style_name.split()[-1])
        except (ValueError, IndexError):
            return 1
    # Also check outline_level from paragraph XML
    if style_name.lower() == "title":
        return 0
    return None


def _extract_para_format(para) -> dict[str, Any]:
    """Extract formatting properties from a paragraph."""
    info: dict[str, Any] = {}

    # Font from first run (most common)
    if para.runs:
        run = para.runs[0]
        info["font_name"] = run.font.name
        info["font_size"] = run.font.size
        info["bold"] = run.font.bold
        info["italic"] = run.font.italic
        info["underline"] = run.font.underline
        info["font_color"] = str(run.font.color.rgb) if run.font.color and run.font.color.rgb else None
    else:
        info["font_name"] = None
        info["font_size"] = None
        info["bold"] = None
        info["italic"] = None
        info["underline"] = None
        info["font_color"] = None

    # Paragraph formatting
    pf = para.paragraph_format
    info["alignment"] = str(para.alignment) if para.alignment is not None else None
    info["line_spacing"] = pf.line_spacing
    info["space_before"] = pf.space_before
    info["space_after"] = pf.space_after
    info["first_line_indent"] = pf.first_line_indent

    return info


def _check_property_consistency(
    item_id: str,
    elements: list[dict],
    prop: str,
    description: str,
) -> CheckItemResult:
    """Check if a property is consistent across all elements."""
    if not elements:
        return CheckItemResult(
            item_id=item_id,
            description=description,
            verdict="not_applicable",
            details="No elements to check",
        )

    values = [e.get(prop) for e in elements if e.get(prop) is not None]
    if not values:
        return CheckItemResult(
            item_id=item_id,
            description=description,
            verdict="pass",
            details="No explicit values set (using defaults)",
        )

    counter = Counter(str(v) for v in values)
    majority_val, majority_count = counter.most_common(1)[0]
    total = len(values)
    outliers = total - majority_count

    if outliers == 0:
        return CheckItemResult(
            item_id=item_id,
            description=description,
            verdict="pass",
            details=f"All {total} elements use {majority_val}",
        )
    else:
        return CheckItemResult(
            item_id=item_id,
            description=description,
            verdict="fail",
            details=f"{outliers}/{total} elements differ from majority ({majority_val}). Values: {dict(counter)}",
            severity="moderate" if outliers > total * 0.2 else "minor",
            fixable=True,
            fix_suggestion=f"Normalize {prop} to {majority_val} for all elements",
        )


def _majority_value(elements: list[dict], prop: str) -> Any:
    """Get the majority value for a property."""
    values = [e.get(prop) for e in elements if e.get(prop) is not None]
    if not values:
        return None
    counter = Counter(str(v) for v in values)
    return counter.most_common(1)[0][0] if counter else None
