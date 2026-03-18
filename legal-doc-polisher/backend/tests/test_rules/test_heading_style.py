"""Tests for heading style rule."""

import pytest
from docx import Document

from app.engine.deterministic.rules.heading_style import HeadingStyleRule
from app.engine.profiler import build_style_profile


def test_detects_deviant_heading(sample_dirty_docx):
    """Should detect the heading with wrong font/size/bold."""
    profile = build_style_profile(sample_dirty_docx)
    doc = Document(str(sample_dirty_docx))
    rule = HeadingStyleRule()

    config = {
        "properties_to_check": ["bold", "underline", "font_name", "font_size", "alignment"],
        "skip_levels": [],
    }

    findings = rule.detect(doc, profile, config)
    # Should find at least the deviant Heading 1
    assert len(findings) >= 1
    assert any("Deviant" in f.location for f in findings)


def test_no_findings_on_clean_doc(sample_clean_docx):
    """A clean document should produce no heading findings."""
    profile = build_style_profile(sample_clean_docx)
    doc = Document(str(sample_clean_docx))
    rule = HeadingStyleRule()

    config = {
        "properties_to_check": ["bold", "font_name", "font_size"],
        "skip_levels": [],
    }

    findings = rule.detect(doc, profile, config)
    assert len(findings) == 0
