"""Paragraph formatting consistency rule.

Detects and fixes body paragraph formatting deviations:
alignment, line spacing, space before/after, first line indent.
"""

from __future__ import annotations

import uuid

from docx import Document
from docx.shared import Pt

from ....models.enums import ChangeSource, Severity
from ....models.schemas import Change, Example, Finding, StyleProfile
from ....utils.docx_helpers import (
    alignment_to_str,
    get_full_text,
    get_heading_level,
    resolve_paragraph_property,
    set_paragraph_spacing,
    str_to_alignment,
)
from .base import Rule


class ParagraphFormatRule(Rule):
    name = "paragraph_format"
    category = "paragraph_format"

    def detect(
        self,
        document: Document,
        profile: StyleProfile,
        config: dict,
        examples: list[Example] | None = None,
    ) -> list[Finding]:
        findings = []
        properties = config.get(
            "properties_to_check",
            ["alignment", "line_spacing", "space_before", "space_after", "first_line_indent"],
        )
        tolerance_pt = config.get("tolerance", {}).get("spacing_pt", 1.0)

        for idx, para in enumerate(document.paragraphs):
            # Only check body text paragraphs
            if get_heading_level(para) is not None:
                continue
            style_name = para.style.name if para.style else ""
            if style_name.startswith("TOC") or style_name.startswith("toc"):
                continue
            text = get_full_text(para).strip()
            if not text:
                continue

            deviations = []

            if "alignment" in properties and profile.body_alignment:
                actual = alignment_to_str(resolve_paragraph_property(para, "alignment"))
                if actual and actual != profile.body_alignment:
                    deviations.append(
                        f"alignment: expected '{profile.body_alignment}', got '{actual}'"
                    )

            if "line_spacing" in properties and profile.body_line_spacing is not None:
                actual = resolve_paragraph_property(para, "line_spacing")
                if actual is not None:
                    actual_val = float(actual)
                    if abs(actual_val - profile.body_line_spacing) > 0.05:
                        deviations.append(
                            f"line spacing: expected {profile.body_line_spacing}, got {actual_val}"
                        )

            if "space_before" in properties and profile.body_space_before_pt is not None:
                actual = resolve_paragraph_property(para, "space_before")
                actual_pt = actual.pt if actual and hasattr(actual, "pt") else None
                if actual_pt is not None:
                    if abs(actual_pt - profile.body_space_before_pt) > tolerance_pt:
                        deviations.append(
                            f"space before: expected {profile.body_space_before_pt}pt, got {actual_pt}pt"
                        )

            if "space_after" in properties and profile.body_space_after_pt is not None:
                actual = resolve_paragraph_property(para, "space_after")
                actual_pt = actual.pt if actual and hasattr(actual, "pt") else None
                if actual_pt is not None:
                    if abs(actual_pt - profile.body_space_after_pt) > tolerance_pt:
                        deviations.append(
                            f"space after: expected {profile.body_space_after_pt}pt, got {actual_pt}pt"
                        )

            if deviations:
                text_preview = text[:60]
                findings.append(
                    Finding(
                        paragraph_index=idx,
                        category=self.category,
                        location=f"Paragraph {idx + 1}: \"{text_preview}...\"",
                        description=f"Paragraph formatting mismatch: {'; '.join(deviations)}",
                        severity=Severity.MINOR,
                        fix_data={
                            "alignment": profile.body_alignment,
                            "line_spacing": profile.body_line_spacing,
                            "space_before": profile.body_space_before_pt,
                            "space_after": profile.body_space_after_pt,
                        },
                    )
                )

        return findings

    def fix(self, document: Document, finding: Finding, profile: StyleProfile) -> Change:
        para = document.paragraphs[finding.paragraph_index]
        fd = finding.fix_data

        alignment = str_to_alignment(fd.get("alignment")) if fd.get("alignment") else None

        set_paragraph_spacing(
            para,
            alignment=alignment,
            line_spacing=fd.get("line_spacing"),
            space_before=fd.get("space_before"),
            space_after=fd.get("space_after"),
        )

        return Change(
            change_id=str(uuid.uuid4()),
            category=self.category,
            location=finding.location,
            description=finding.description,
            severity=finding.severity,
            source=ChangeSource.DETERMINISTIC,
        )
