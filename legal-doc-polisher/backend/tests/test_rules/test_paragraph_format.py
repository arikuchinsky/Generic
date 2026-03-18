"""Tests for paragraph format rule."""

from docx import Document

from app.engine.deterministic.rules.paragraph_format import ParagraphFormatRule
from app.engine.profiler import build_style_profile


def test_detects_alignment_mismatch(sample_dirty_docx):
    """Should detect left-aligned paragraph when dominant is justify."""
    profile = build_style_profile(sample_dirty_docx)
    doc = Document(str(sample_dirty_docx))
    rule = ParagraphFormatRule()

    config = {
        "properties_to_check": ["alignment"],
        "tolerance": {"spacing_pt": 1.0},
    }

    findings = rule.detect(doc, profile, config)
    # Should find the left-aligned paragraph
    assert len(findings) >= 1
