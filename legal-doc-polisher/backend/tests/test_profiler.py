"""Tests for the document style profiler."""

import pytest
from app.engine.profiler import build_style_profile


def test_profile_clean_document(sample_clean_docx):
    """A clean document should produce a clear style profile."""
    profile = build_style_profile(sample_clean_docx)

    # Should detect heading level 1
    assert 1 in profile.heading_styles
    h1 = profile.heading_styles[1]
    assert h1.bold is True
    assert h1.font_name == "Times New Roman"

    # Body should be Times New Roman
    assert profile.body_font.name == "Times New Roman"


def test_profile_dirty_document(sample_dirty_docx):
    """A dirty document should still produce a majority-based profile."""
    profile = build_style_profile(sample_dirty_docx)

    # Majority of H1s are TNR bold — the deviant should not change the profile
    assert 1 in profile.heading_styles
    h1 = profile.heading_styles[1]
    assert h1.bold is True
    assert h1.font_name == "Times New Roman"


def test_quote_profile_always_smart(sample_dirty_docx):
    """Quote style should always be 'smart' for legal docs."""
    profile = build_style_profile(sample_dirty_docx)
    assert profile.quote_style == "smart"
