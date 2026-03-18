"""Heading style consistency rule.

Detects and fixes mismatched heading formatting (bold, underline, font name,
font size, alignment, numbering) by comparing each heading against the
dominant style for its level from the StyleProfile.
"""

from __future__ import annotations

import uuid

from docx import Document

from ....models.enums import ChangeSource, Severity
from ....models.schemas import Change, Example, Finding, StyleProfile
from ....utils.docx_helpers import (
    alignment_to_str,
    get_heading_level,
    resolve_font_property,
    resolve_paragraph_property,
    set_run_font_properties,
    str_to_alignment,
)
from .base import Rule


class HeadingStyleRule(Rule):
    name = "heading_style"
    category = "heading_style"

    def detect(
        self,
        document: Document,
        profile: StyleProfile,
        config: dict,
        examples: list[Example] | None = None,
    ) -> list[Finding]:
        findings = []
        properties_to_check = config.get(
            "properties_to_check", ["bold", "underline", "font_name", "font_size", "alignment"]
        )
        skip_levels = set(config.get("skip_levels", []))

        for idx, para in enumerate(document.paragraphs):
            level = get_heading_level(para)
            if level is None or level in skip_levels:
                continue
            if level not in profile.heading_styles:
                continue

            expected = profile.heading_styles[level]
            deviations = []

            if not para.runs:
                continue

            run = para.runs[0]

            # Check each property
            if "bold" in properties_to_check and expected.bold is not None:
                actual = resolve_font_property(run, "bold")
                if actual != expected.bold:
                    deviations.append(
                        f"bold: expected {expected.bold}, got {actual}"
                    )

            if "underline" in properties_to_check and expected.underline is not None:
                actual = resolve_font_property(run, "underline")
                if actual != expected.underline:
                    deviations.append(
                        f"underline: expected {expected.underline}, got {actual}"
                    )

            if "font_name" in properties_to_check and expected.font_name is not None:
                actual = resolve_font_property(run, "name")
                if actual and actual != expected.font_name:
                    deviations.append(
                        f"font: expected '{expected.font_name}', got '{actual}'"
                    )

            if "font_size" in properties_to_check and expected.font_size_pt is not None:
                actual = resolve_font_property(run, "size")
                actual_pt = actual.pt if actual and hasattr(actual, "pt") else None
                if actual_pt and abs(actual_pt - expected.font_size_pt) > 0.5:
                    deviations.append(
                        f"size: expected {expected.font_size_pt}pt, got {actual_pt}pt"
                    )

            if "alignment" in properties_to_check and expected.alignment is not None:
                actual = alignment_to_str(resolve_paragraph_property(para, "alignment"))
                if actual and actual != expected.alignment:
                    deviations.append(
                        f"alignment: expected '{expected.alignment}', got '{actual}'"
                    )

            if deviations:
                text_preview = para.text[:60].strip()
                findings.append(
                    Finding(
                        paragraph_index=idx,
                        run_index=0,
                        category=self.category,
                        location=f"Paragraph {idx + 1}, Heading {level}: \"{text_preview}...\"",
                        description=f"Heading {level} formatting mismatch: {'; '.join(deviations)}",
                        severity=Severity.MODERATE,
                        fix_data={
                            "level": level,
                            "expected_bold": expected.bold,
                            "expected_underline": expected.underline,
                            "expected_font_name": expected.font_name,
                            "expected_font_size_pt": expected.font_size_pt,
                            "expected_alignment": expected.alignment,
                        },
                    )
                )

        return findings

    def fix(self, document: Document, finding: Finding, profile: StyleProfile) -> Change:
        para = document.paragraphs[finding.paragraph_index]
        fd = finding.fix_data

        # Apply formatting to ALL runs in the heading
        for run in para.runs:
            set_run_font_properties(
                run,
                bold=fd.get("expected_bold"),
                underline=fd.get("expected_underline"),
                font_name=fd.get("expected_font_name"),
                font_size=fd.get("expected_font_size_pt"),
            )

        # Fix alignment
        if fd.get("expected_alignment"):
            alignment = str_to_alignment(fd["expected_alignment"])
            if alignment is not None:
                para.paragraph_format.alignment = alignment

        return Change(
            change_id=str(uuid.uuid4()),
            category=self.category,
            location=finding.location,
            description=finding.description,
            severity=finding.severity,
            source=ChangeSource.DETERMINISTIC,
        )
