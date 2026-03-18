"""Low-level OOXML / python-docx utilities for direct XML manipulation.

This module provides functions to:
- Resolve inherited font and paragraph properties through the style chain
- Access and manipulate raw OOXML elements (w:rPr, w:pPr, w:numPr, etc.)
- Extract numbering definitions and abstract numbering info
- Work with document defaults and style hierarchy
"""

from __future__ import annotations

import re
from typing import Any
from xml.etree.ElementTree import Element

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Emu, Pt, Twips
from docx.text.paragraph import Paragraph
from docx.text.run import Run

# OOXML namespace map for direct XPath/element operations
OOXML_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
}


# ---------------------------------------------------------------------------
# Style inheritance resolution
# ---------------------------------------------------------------------------


def resolve_font_property(run: Run, prop: str) -> Any:
    """Resolve a font property by walking the style inheritance chain.

    Order: run direct formatting -> paragraph style -> base styles -> doc defaults.

    Args:
        run: The python-docx Run object.
        prop: Font property name (e.g., 'bold', 'name', 'size', 'underline', 'color').

    Returns:
        The resolved property value, or None if not set anywhere.
    """
    # 1. Direct run formatting
    val = getattr(run.font, prop, None)
    if val is not None:
        return val

    # 2. Walk the paragraph's style chain
    style = run.style if run.style else None
    if style is None:
        # Fall back to paragraph style
        try:
            para = run._element.getparent()
            if para is not None:
                para_obj = Paragraph(para, run._element.getparent().getparent())
                style = para_obj.style
        except (AttributeError, TypeError):
            style = None

    while style is not None:
        font = style.font
        if font is not None:
            val = getattr(font, prop, None)
            if val is not None:
                return val
        style = style.base_style

    # 3. Document defaults (accessed via raw XML)
    return _get_doc_default_font_prop(run, prop)


def resolve_paragraph_property(para: Paragraph, prop: str) -> Any:
    """Resolve a paragraph format property through the style chain.

    Args:
        para: The python-docx Paragraph object.
        prop: ParagraphFormat property (e.g., 'alignment', 'line_spacing',
              'space_before', 'space_after', 'first_line_indent').

    Returns:
        The resolved value, or None.
    """
    # 1. Direct paragraph formatting
    pf = para.paragraph_format
    val = getattr(pf, prop, None)
    if val is not None:
        return val

    # 2. Walk style chain
    style = para.style
    while style is not None:
        if style.paragraph_format is not None:
            val = getattr(style.paragraph_format, prop, None)
            if val is not None:
                return val
        style = style.base_style

    return None


def _get_doc_default_font_prop(run: Run, prop: str) -> Any:
    """Extract a font property from w:docDefaults in the styles part."""
    try:
        doc_element = run._element
        # Walk up to find the document root
        root = doc_element
        while root.getparent() is not None:
            root = root.getparent()
        # Find styles element
        styles_parts = root.findall(".//" + qn("w:docDefaults"))
        if not styles_parts:
            return None
        # Try rPrDefault -> rPr
        for doc_defaults in styles_parts:
            rpr_default = doc_defaults.find(qn("w:rPrDefault"))
            if rpr_default is not None:
                rpr = rpr_default.find(qn("w:rPr"))
                if rpr is not None:
                    return _extract_rpr_property(rpr, prop)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Raw OOXML element access
# ---------------------------------------------------------------------------


def get_rpr_element(run: Run) -> Element | None:
    """Get the w:rPr (run properties) element for a run."""
    return run._element.find(qn("w:rPr"))


def get_ppr_element(para: Paragraph) -> Element | None:
    """Get the w:pPr (paragraph properties) element for a paragraph."""
    return para._element.find(qn("w:pPr"))


def get_num_pr(para: Paragraph) -> tuple[str | None, int | None]:
    """Extract numbering properties (numId, ilvl) from a paragraph.

    Returns:
        Tuple of (numId, ilvl) or (None, None) if not numbered.
    """
    ppr = get_ppr_element(para)
    if ppr is None:
        return None, None

    num_pr = ppr.find(qn("w:numPr"))
    if num_pr is None:
        # Check style's numbering
        style = para.style
        while style is not None:
            style_el = style._element
            if style_el is not None:
                s_ppr = style_el.find(qn("w:pPr"))
                if s_ppr is not None:
                    s_num_pr = s_ppr.find(qn("w:numPr"))
                    if s_num_pr is not None:
                        num_pr = s_num_pr
                        break
            style = style.base_style

    if num_pr is None:
        return None, None

    num_id_el = num_pr.find(qn("w:numId"))
    ilvl_el = num_pr.find(qn("w:ilvl"))

    num_id = num_id_el.get(qn("w:val")) if num_id_el is not None else None
    ilvl = int(ilvl_el.get(qn("w:val"))) if ilvl_el is not None else 0

    return num_id, ilvl


def set_num_pr(para: Paragraph, num_id: str, ilvl: int = 0) -> None:
    """Set or replace numbering properties on a paragraph via direct XML."""
    ppr = get_ppr_element(para)
    if ppr is None:
        ppr = para._element.makeelement(qn("w:pPr"), {})
        para._element.insert(0, ppr)

    # Remove existing numPr
    existing = ppr.find(qn("w:numPr"))
    if existing is not None:
        ppr.remove(existing)

    # Build new numPr element
    num_pr = ppr.makeelement(qn("w:numPr"), {})
    ilvl_el = num_pr.makeelement(qn("w:ilvl"), {qn("w:val"): str(ilvl)})
    num_id_el = num_pr.makeelement(qn("w:numId"), {qn("w:val"): str(num_id)})
    num_pr.append(ilvl_el)
    num_pr.append(num_id_el)
    ppr.append(num_pr)


def get_numbering_definitions(doc: Document) -> dict[str, dict]:
    """Extract all numbering definitions from the document's numbering part.

    Returns:
        Dict mapping numId -> {abstract_num_id, levels: {ilvl: {numFmt, lvlText, start}}}
    """
    result = {}
    try:
        numbering_part = doc.part.numbering_part
        if numbering_part is None:
            return result
        numbering_element = numbering_part._element
    except Exception:
        return result

    # Parse w:num elements (concrete numbering instances)
    for num_el in numbering_element.findall(qn("w:num")):
        num_id = num_el.get(qn("w:numId"))
        abstract_ref = num_el.find(qn("w:abstractNumId"))
        if abstract_ref is not None:
            abstract_id = abstract_ref.get(qn("w:val"))
            result[num_id] = {"abstract_num_id": abstract_id, "levels": {}}

    # Parse w:abstractNum elements for level definitions
    abstract_nums = {}
    for abstract_el in numbering_element.findall(qn("w:abstractNum")):
        abs_id = abstract_el.get(qn("w:abstractNumId"))
        levels = {}
        for lvl_el in abstract_el.findall(qn("w:lvl")):
            ilvl = int(lvl_el.get(qn("w:ilvl"), "0"))
            num_fmt_el = lvl_el.find(qn("w:numFmt"))
            lvl_text_el = lvl_el.find(qn("w:lvlText"))
            start_el = lvl_el.find(qn("w:start"))
            levels[ilvl] = {
                "numFmt": num_fmt_el.get(qn("w:val")) if num_fmt_el is not None else None,
                "lvlText": lvl_text_el.get(qn("w:val")) if lvl_text_el is not None else None,
                "start": int(start_el.get(qn("w:val"))) if start_el is not None else 1,
            }
        abstract_nums[abs_id] = levels

    # Link concrete nums to their abstract level definitions
    for num_id, info in result.items():
        abs_id = info["abstract_num_id"]
        if abs_id in abstract_nums:
            info["levels"] = abstract_nums[abs_id]

    return result


def _extract_rpr_property(rpr: Element, prop: str) -> Any:
    """Extract a specific property value from a w:rPr element."""
    prop_map = {
        "bold": ("w:b", "w:val", True),
        "underline": ("w:u", "w:val", True),
        "name": ("w:rFonts", "w:ascii", None),
        "size": ("w:sz", "w:val", None),
        "color": ("w:color", "w:val", None),
    }
    if prop not in prop_map:
        return None

    tag, attr, toggle_default = prop_map[prop]
    el = rpr.find(qn(tag))
    if el is None:
        return None

    if prop in ("bold", "underline"):
        val = el.get(qn(attr))
        if val is None:
            return toggle_default
        return val.lower() not in ("0", "false", "off")
    elif prop == "size":
        val = el.get(qn(attr))
        return Pt(int(val) / 2) if val else None
    else:
        return el.get(qn(attr))


# ---------------------------------------------------------------------------
# Paragraph classification and text helpers
# ---------------------------------------------------------------------------


def get_heading_level(para: Paragraph) -> int | None:
    """Return the heading level (1-9) if this is a heading paragraph, else None."""
    style_name = para.style.name if para.style else ""
    match = re.match(r"Heading\s+(\d+)", style_name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def get_full_text(para: Paragraph) -> str:
    """Get the full text of a paragraph including all runs."""
    return "".join(run.text for run in para.runs)


def iter_paragraphs_with_index(doc: Document):
    """Yield (index, paragraph) for all paragraphs in the document body."""
    for idx, para in enumerate(doc.paragraphs):
        yield idx, para


def find_page_breaks(doc: Document) -> list[int]:
    """Find paragraph indices where hard page breaks occur.

    Returns a list of paragraph indices that contain or follow a page break.
    """
    breaks = []
    for idx, para in enumerate(doc.paragraphs):
        # Check for page break before paragraph (in pPr)
        ppr = get_ppr_element(para)
        if ppr is not None:
            page_break = ppr.find(qn("w:pageBreakBefore"))
            if page_break is not None:
                val = page_break.get(qn("w:val"))
                if val is None or val.lower() not in ("0", "false", "off"):
                    breaks.append(idx)
                    continue

        # Check for page break in runs
        for run in para.runs:
            for br in run._element.findall(qn("w:br")):
                if br.get(qn("w:type")) == "page":
                    breaks.append(idx)
                    break
    return breaks


def set_run_font_properties(
    run: Run,
    bold: bool | None = None,
    underline: bool | None = None,
    font_name: str | None = None,
    font_size: float | None = None,
) -> None:
    """Set font properties on a run, including via direct OOXML when needed."""
    if bold is not None:
        run.font.bold = bold
    if underline is not None:
        run.font.underline = underline
    if font_name is not None:
        run.font.name = font_name
        # Also set the OOXML rFonts element for full compatibility
        rpr = run._element.find(qn("w:rPr"))
        if rpr is None:
            rpr = run._element.makeelement(qn("w:rPr"), {})
            run._element.insert(0, rpr)
        r_fonts = rpr.find(qn("w:rFonts"))
        if r_fonts is None:
            r_fonts = rpr.makeelement(qn("w:rFonts"), {})
            rpr.append(r_fonts)
        r_fonts.set(qn("w:ascii"), font_name)
        r_fonts.set(qn("w:hAnsi"), font_name)
        r_fonts.set(qn("w:cs"), font_name)
    if font_size is not None:
        run.font.size = Pt(font_size)


def set_paragraph_spacing(
    para: Paragraph,
    alignment: int | None = None,
    line_spacing: float | None = None,
    space_before: float | None = None,
    space_after: float | None = None,
    first_line_indent: float | None = None,
) -> None:
    """Set paragraph formatting properties."""
    pf = para.paragraph_format
    if alignment is not None:
        pf.alignment = alignment
    if line_spacing is not None:
        pf.line_spacing = line_spacing
    if space_before is not None:
        pf.space_before = Pt(space_before)
    if space_after is not None:
        pf.space_after = Pt(space_after)
    if first_line_indent is not None:
        pf.first_line_indent = Pt(first_line_indent)


def alignment_to_str(alignment) -> str | None:
    """Convert a WD_ALIGN_PARAGRAPH value to a string."""
    if alignment is None:
        return None
    mapping = {
        WD_ALIGN_PARAGRAPH.LEFT: "left",
        WD_ALIGN_PARAGRAPH.CENTER: "center",
        WD_ALIGN_PARAGRAPH.RIGHT: "right",
        WD_ALIGN_PARAGRAPH.JUSTIFY: "justify",
    }
    return mapping.get(alignment, str(alignment))


def str_to_alignment(s: str | None):
    """Convert a string alignment back to WD_ALIGN_PARAGRAPH."""
    if s is None:
        return None
    mapping = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }
    return mapping.get(s.lower())
