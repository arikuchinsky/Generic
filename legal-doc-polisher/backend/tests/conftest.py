"""Shared test fixtures for the Legal Document Polisher."""

import os
from pathlib import Path

import pytest
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH


FIXTURES_DIR = Path(__file__).parent / "test_rules" / "fixtures"


@pytest.fixture
def fixtures_dir():
    """Path to the test fixtures directory."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    return FIXTURES_DIR


@pytest.fixture
def sample_clean_docx(fixtures_dir):
    """Create a clean sample .docx with consistent formatting."""
    path = fixtures_dir / "sample_clean.docx"
    doc = Document()

    # Set up consistent heading styles
    for i in range(3):
        heading = doc.add_heading(f"Section {i + 1}: Clean Heading", level=1)
        for run in heading.runs:
            run.font.name = "Times New Roman"
            run.font.size = Pt(14)
            run.font.bold = True

        para = doc.add_paragraph("This is body text with consistent formatting.")
        for run in para.runs:
            run.font.name = "Times New Roman"
            run.font.size = Pt(12)
        para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        sub = doc.add_heading(f"Subsection {i + 1}.1", level=2)
        for run in sub.runs:
            run.font.name = "Times New Roman"
            run.font.size = Pt(12)
            run.font.bold = True

        doc.add_paragraph(
            "\u201CThis is a properly quoted sentence with smart quotes.\u201D"
        )

    doc.save(str(path))
    return path


@pytest.fixture
def sample_dirty_docx(fixtures_dir):
    """Create a dirty sample .docx with various formatting issues."""
    path = fixtures_dir / "sample_dirty.docx"
    doc = Document()

    # Heading 1 — consistent (3 instances)
    for i in range(3):
        heading = doc.add_heading(f"Section {i + 1}: Main Heading", level=1)
        for run in heading.runs:
            run.font.name = "Times New Roman"
            run.font.size = Pt(14)
            run.font.bold = True

        # Body text with inconsistency on the second iteration
        para = doc.add_paragraph("This is body text.")
        for run in para.runs:
            run.font.name = "Times New Roman"
            run.font.size = Pt(12)
        para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # Now add a deviant heading (wrong font)
    bad_heading = doc.add_heading("Section 4: Deviant Heading", level=1)
    for run in bad_heading.runs:
        run.font.name = "Calibri"  # Wrong!
        run.font.size = Pt(11)     # Wrong!
        run.font.bold = False      # Wrong!

    # Straight quotes
    doc.add_paragraph('This has "straight quotes" that should be smart.')

    # Duplicate list labels
    doc.add_paragraph("(a) First item")
    doc.add_paragraph("(a) Second item — duplicate label!")
    doc.add_paragraph("(c) Third item")

    # Inconsistent body alignment
    mis = doc.add_paragraph("This paragraph is left-aligned instead of justified.")
    mis.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    doc.save(str(path))
    return path
