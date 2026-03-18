"""Header/footer consistency rule for legal documents.

Common CRE doc issues:
- Inconsistent header/footer font across sections
- Page numbering format mismatches
- Missing or inconsistent document title in headers
- Different header/footer content on odd vs even pages when not intended
"""

from __future__ import annotations

import re
import uuid
from collections import Counter

from docx import Document
from docx.oxml.ns import qn

from ....models.enums import ChangeSource, Severity
from ....models.schemas import Change, Example, Finding, StyleProfile
from .base import Rule


class HeaderFooterRule(Rule):
    name = "header_footer"
    category = "header_footer"

    def detect(
        self,
        document: Document,
        profile: StyleProfile,
        config: dict,
        examples: list[Example] | None = None,
    ) -> list[Finding]:
        findings = []

        findings.extend(self._check_header_consistency(document))
        findings.extend(self._check_footer_consistency(document))
        findings.extend(self._check_page_numbering(document))

        return findings

    def _check_header_consistency(self, document: Document) -> list[Finding]:
        """Check that headers use consistent formatting across all sections."""
        findings = []
        header_fonts = []
        header_sizes = []

        for section_idx, section in enumerate(document.sections):
            header = section.header
            if header.is_linked_to_previous:
                continue
            for para in header.paragraphs:
                for run in para.runs:
                    if run.text.strip():
                        font_name = run.font.name
                        font_size = run.font.size
                        if font_name:
                            header_fonts.append((section_idx, font_name))
                        if font_size:
                            header_sizes.append((section_idx, font_size))

        # Check font consistency
        if header_fonts:
            names = [f[1] for f in header_fonts]
            if len(set(names)) > 1:
                dominant = Counter(names).most_common(1)[0][0]
                for sect_idx, name in header_fonts:
                    if name != dominant:
                        findings.append(
                            Finding(
                                category=self.category,
                                location=f"Section {sect_idx + 1} header",
                                description=(
                                    f"Header font '{name}' differs from "
                                    f"dominant '{dominant}'"
                                ),
                                severity=Severity.MODERATE,
                                fix_data={
                                    "type": "header_font",
                                    "section_idx": sect_idx,
                                    "expected_font": dominant,
                                },
                            )
                        )

        return findings

    def _check_footer_consistency(self, document: Document) -> list[Finding]:
        """Check footer formatting consistency."""
        findings = []
        footer_fonts = []

        for section_idx, section in enumerate(document.sections):
            footer = section.footer
            if footer.is_linked_to_previous:
                continue
            for para in footer.paragraphs:
                for run in para.runs:
                    if run.text.strip():
                        font_name = run.font.name
                        if font_name:
                            footer_fonts.append((section_idx, font_name))

        if footer_fonts:
            names = [f[1] for f in footer_fonts]
            if len(set(names)) > 1:
                dominant = Counter(names).most_common(1)[0][0]
                for sect_idx, name in footer_fonts:
                    if name != dominant:
                        findings.append(
                            Finding(
                                category=self.category,
                                location=f"Section {sect_idx + 1} footer",
                                description=(
                                    f"Footer font '{name}' differs from "
                                    f"dominant '{dominant}'"
                                ),
                                severity=Severity.MODERATE,
                                fix_data={
                                    "type": "footer_font",
                                    "section_idx": sect_idx,
                                    "expected_font": dominant,
                                },
                            )
                        )

        return findings

    def _check_page_numbering(self, document: Document) -> list[Finding]:
        """Check for page numbering consistency across sections."""
        findings = []
        num_formats = []

        for section_idx, section in enumerate(document.sections):
            # Check footer for page number fields
            footer = section.footer
            for para in footer.paragraphs:
                xml_str = para._element.xml
                # Look for PAGE field codes
                if "PAGE" in xml_str or "fldChar" in xml_str:
                    # Detect format from surrounding text
                    text = "".join(r.text for r in para.runs)
                    if re.search(r"Page\s+\d", text):
                        num_formats.append((section_idx, "Page N"))
                    elif re.search(r"- \d+ -", text):
                        num_formats.append((section_idx, "- N -"))
                    elif re.search(r"\d+\s+of\s+\d+", text):
                        num_formats.append((section_idx, "N of M"))
                    else:
                        num_formats.append((section_idx, "plain"))

        if len(num_formats) >= 2:
            formats = [f[1] for f in num_formats]
            if len(set(formats)) > 1:
                dominant = Counter(formats).most_common(1)[0][0]
                for sect_idx, fmt in num_formats:
                    if fmt != dominant:
                        findings.append(
                            Finding(
                                category=self.category,
                                location=f"Section {sect_idx + 1} footer",
                                description=(
                                    f"Page numbering format '{fmt}' differs from "
                                    f"dominant '{dominant}'"
                                ),
                                severity=Severity.MODERATE,
                                fix_data={
                                    "type": "page_number_format",
                                    "section_idx": sect_idx,
                                },
                            )
                        )

        return findings

    def fix(self, document: Document, finding: Finding, profile: StyleProfile) -> Change:
        fd = finding.fix_data

        if fd.get("type") in ("header_font", "footer_font"):
            sect_idx = fd.get("section_idx", 0)
            expected_font = fd.get("expected_font")
            if sect_idx < len(document.sections) and expected_font:
                section = document.sections[sect_idx]
                target = section.header if fd["type"] == "header_font" else section.footer
                for para in target.paragraphs:
                    for run in para.runs:
                        run.font.name = expected_font

        return Change(
            change_id=str(uuid.uuid4()),
            category=self.category,
            location=finding.location,
            description=finding.description,
            severity=finding.severity,
            source=ChangeSource.DETERMINISTIC,
        )
