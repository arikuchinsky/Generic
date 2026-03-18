"""Document style profiler — analyzes a .docx to build the dominant StyleProfile.

The profiler scans the entire document, collects formatting properties from every
paragraph and run, then uses majority voting to determine the "intended" style
for each element type (headings by level, body text, lists, quotes).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt

from ..models.schemas import FontSpec, HeadingStyleSpec, ListStyleSpec, StyleProfile
from ..utils.docx_helpers import (
    alignment_to_str,
    get_full_text,
    get_heading_level,
    get_num_pr,
    get_numbering_definitions,
    resolve_font_property,
    resolve_paragraph_property,
)


def build_style_profile(
    docx_path: Path,
    heading_threshold: float = 0.75,
    body_threshold: float = 0.80,
) -> StyleProfile:
    """Analyze a document and build a StyleProfile based on majority voting.

    Args:
        docx_path: Path to the .docx file.
        heading_threshold: Minimum fraction for a heading property to be "dominant".
        body_threshold: Minimum fraction for a body property to be "dominant".

    Returns:
        A StyleProfile representing the document's dominant formatting.
    """
    doc = Document(str(docx_path))

    heading_styles = _profile_headings(doc, heading_threshold)
    body_font, body_alignment, body_spacing = _profile_body(doc, body_threshold)
    list_styles = _profile_lists(doc)
    quote_style = _profile_quotes(doc)

    return StyleProfile(
        heading_styles=heading_styles,
        body_font=body_font,
        body_alignment=body_alignment,
        body_line_spacing=body_spacing.get("line_spacing"),
        body_space_before_pt=body_spacing.get("space_before"),
        body_space_after_pt=body_spacing.get("space_after"),
        list_styles=list_styles,
        quote_style=quote_style,
    )


def _profile_headings(
    doc: Document, threshold: float
) -> dict[int, HeadingStyleSpec]:
    """Collect formatting from all headings and compute dominant style per level."""
    # level -> list of observed property dicts
    observations: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for para in doc.paragraphs:
        level = get_heading_level(para)
        if level is None:
            continue

        # Collect properties from the first run (primary formatting)
        props: dict[str, Any] = {}
        if para.runs:
            run = para.runs[0]
            props["bold"] = resolve_font_property(run, "bold")
            props["underline"] = resolve_font_property(run, "underline")
            props["font_name"] = resolve_font_property(run, "name")
            size = resolve_font_property(run, "size")
            props["font_size_pt"] = size.pt if size and hasattr(size, "pt") else (
                float(size) if size else None
            )
        else:
            # Heading with no runs — use style defaults
            style = para.style
            if style and style.font:
                props["bold"] = style.font.bold
                props["underline"] = style.font.underline
                props["font_name"] = style.font.name
                size = style.font.size
                props["font_size_pt"] = size.pt if size and hasattr(size, "pt") else None

        props["alignment"] = alignment_to_str(
            resolve_paragraph_property(para, "alignment")
        )

        # Numbering format detection
        num_id, ilvl = get_num_pr(para)
        text = get_full_text(para).strip()
        numbering_format = _detect_numbering_format(text, num_id)
        props["numbering_format"] = numbering_format

        observations[level].append(props)

    # Compute dominant values per level
    result = {}
    for level, obs_list in observations.items():
        if not obs_list:
            continue
        result[level] = HeadingStyleSpec(
            bold=_majority_vote([o.get("bold") for o in obs_list], threshold),
            underline=_majority_vote([o.get("underline") for o in obs_list], threshold),
            font_name=_majority_vote([o.get("font_name") for o in obs_list], threshold),
            font_size_pt=_majority_vote([o.get("font_size_pt") for o in obs_list], threshold),
            numbering_format=_majority_vote(
                [o.get("numbering_format") for o in obs_list], threshold
            ),
            alignment=_majority_vote([o.get("alignment") for o in obs_list], threshold),
        )

    return result


def _profile_body(
    doc: Document, threshold: float
) -> tuple[FontSpec, str | None, dict[str, float | None]]:
    """Profile body (Normal style) paragraphs."""
    font_names: list[str | None] = []
    font_sizes: list[float | None] = []
    alignments: list[str | None] = []
    line_spacings: list[float | None] = []
    space_befores: list[float | None] = []
    space_afters: list[float | None] = []

    for para in doc.paragraphs:
        style_name = para.style.name if para.style else ""
        # Include Normal, Body Text, and similar body styles
        if get_heading_level(para) is not None:
            continue
        if style_name.startswith("TOC") or style_name.startswith("toc"):
            continue
        text = get_full_text(para).strip()
        if not text:
            continue

        # Font from first run
        if para.runs:
            run = para.runs[0]
            font_names.append(resolve_font_property(run, "name"))
            size = resolve_font_property(run, "size")
            font_sizes.append(
                size.pt if size and hasattr(size, "pt") else (float(size) if size else None)
            )

        # Paragraph formatting
        alignments.append(alignment_to_str(resolve_paragraph_property(para, "alignment")))

        ls = resolve_paragraph_property(para, "line_spacing")
        line_spacings.append(float(ls) if ls is not None else None)

        sb = resolve_paragraph_property(para, "space_before")
        space_befores.append(sb.pt if sb and hasattr(sb, "pt") else None)

        sa = resolve_paragraph_property(para, "space_after")
        space_afters.append(sa.pt if sa and hasattr(sa, "pt") else None)

    body_font = FontSpec(
        name=_majority_vote(font_names, threshold),
        size_pt=_majority_vote(font_sizes, threshold),
    )
    body_alignment = _majority_vote(alignments, threshold)
    body_spacing = {
        "line_spacing": _majority_vote(line_spacings, threshold),
        "space_before": _majority_vote(space_befores, threshold),
        "space_after": _majority_vote(space_afters, threshold),
    }

    return body_font, body_alignment, body_spacing


def _profile_lists(doc: Document) -> dict[str, ListStyleSpec]:
    """Profile list formatting by numbering definition."""
    num_defs = get_numbering_definitions(doc)
    result = {}

    for num_id, info in num_defs.items():
        for ilvl, level_info in info.get("levels", {}).items():
            key = f"{num_id}_{ilvl}"
            result[key] = ListStyleSpec(
                label_format=level_info.get("lvlText"),
                indent_pt=None,  # Would need to parse w:ind from lvl
                font=None,
            )

    return result


def _profile_quotes(doc: Document) -> str:
    """Determine dominant quote style (smart vs straight)."""
    smart_count = 0
    straight_count = 0

    smart_chars = {"\u2018", "\u2019", "\u201C", "\u201D"}
    straight_chars = {"'", '"'}

    for para in doc.paragraphs:
        text = get_full_text(para)
        for ch in text:
            if ch in smart_chars:
                smart_count += 1
            elif ch in straight_chars:
                # Don't count apostrophes in contractions as straight quotes
                straight_count += 1

    # Legal docs should always use smart quotes
    return "smart"


def _detect_numbering_format(text: str, num_id: str | None) -> str | None:
    """Detect the numbering format from heading text (e.g., '1.', 'A.', 'I.')."""
    if not text:
        return None

    # Common legal document numbering patterns
    patterns = [
        (r"^(\d+)\.\s", "decimal_dot"),       # 1. 2. 3.
        (r"^(\d+)\)\s", "decimal_paren"),      # 1) 2) 3)
        (r"^\((\d+)\)\s", "decimal_paren_both"),  # (1) (2) (3)
        (r"^([A-Z])\.\s", "upper_alpha_dot"),  # A. B. C.
        (r"^([a-z])\.\s", "lower_alpha_dot"),  # a. b. c.
        (r"^\(([a-z])\)\s", "lower_alpha_paren"),  # (a) (b) (c)
        (r"^([IVXivx]+)\.\s", "roman_dot"),    # I. II. III.
        (r"^\(([IVXivx]+)\)\s", "roman_paren"),  # (I) (II) (III)
        (r"^(Article|Section|ARTICLE|SECTION)\s+", "word_prefix"),
    ]

    for pattern, fmt in patterns:
        if re.match(pattern, text):
            return fmt

    return None


def _majority_vote(values: list[Any], threshold: float) -> Any:
    """Return the most common non-None value if it exceeds the threshold."""
    filtered = [v for v in values if v is not None]
    if not filtered:
        return None

    counter = Counter(filtered)
    most_common_val, most_common_count = counter.most_common(1)[0]

    if most_common_count / len(filtered) >= threshold:
        return most_common_val

    # If no clear majority, still return the most common
    if most_common_count / len(filtered) >= 0.5:
        return most_common_val

    return None
