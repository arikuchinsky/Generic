"""Tests for list labels rule."""

from docx import Document

from app.engine.deterministic.rules.list_labels import ListLabelsRule
from app.engine.profiler import build_style_profile


def test_detects_duplicate_labels(sample_dirty_docx):
    """Should detect the duplicate '(a)' label."""
    profile = build_style_profile(sample_dirty_docx)
    doc = Document(str(sample_dirty_docx))
    rule = ListLabelsRule()

    config = {
        "check_sequence": True,
        "check_format_consistency": True,
        "check_nesting": True,
    }

    findings = rule.detect(doc, profile, config)
    # Should find the duplicate "(a)"
    dup_findings = [f for f in findings if "duplicate" in f.description.lower()]
    assert len(dup_findings) >= 1
