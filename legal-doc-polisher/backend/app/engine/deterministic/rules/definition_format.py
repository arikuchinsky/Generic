"""Definition section formatting rule for CRE legal documents.

Common issues in commercial real estate docs:
- Inconsistent formatting of defined terms (some bold, some quoted, some both)
- Definitions not in alphabetical order
- Defined terms used without definition
- Definition formatting doesn't match the convention (e.g., "Term" means... vs "Term" shall mean...)
- Inconsistent use of bold/italic/underline for defined terms
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict

from docx import Document

from ....models.enums import ChangeSource, Severity
from ....models.schemas import Change, Example, Finding, StyleProfile
from ....utils.docx_helpers import get_full_text, get_heading_level, resolve_font_property
from .base import Rule

# Pattern to detect defined terms in definitions section
DEFINITION_PATTERNS = [
    # "Term" means / shall mean
    re.compile(r'^["\u201C]([A-Z][A-Za-z\s\-/]+)["\u201D]\s+(?:means|shall mean|has the meaning)', re.IGNORECASE),
    # "Term" is defined as
    re.compile(r'^["\u201C]([A-Z][A-Za-z\s\-/]+)["\u201D]\s+(?:is defined|refers to)', re.IGNORECASE),
    # (bold) Term means
    re.compile(r'^([A-Z][A-Za-z\s\-/]+)\.\s+(?:means|shall mean)', re.IGNORECASE),
]

# Pattern to detect usage of defined terms (capitalized multi-word terms in quotes)
DEFINED_TERM_USAGE = re.compile(r'["\u201C]([A-Z][A-Za-z\s\-/]{2,})["\u201D]')


class DefinitionFormatRule(Rule):
    name = "definition_format"
    category = "definition_format"

    def detect(
        self,
        document: Document,
        profile: StyleProfile,
        config: dict,
        examples: list[Example] | None = None,
    ) -> list[Finding]:
        findings = []

        # Collect all definitions and their formatting
        definitions = self._collect_definitions(document)

        # Check formatting consistency among definitions
        findings.extend(self._check_definition_formatting(document, definitions))

        # Check alphabetical order
        findings.extend(self._check_alphabetical_order(document, definitions))

        # Check for defined terms used but never defined
        findings.extend(self._check_undefined_terms(document, definitions))

        return findings

    def _collect_definitions(
        self, document: Document
    ) -> list[dict]:
        """Collect all defined terms and their formatting properties."""
        definitions = []
        in_definitions_section = False

        for idx, para in enumerate(document.paragraphs):
            text = get_full_text(para).strip()
            level = get_heading_level(para)

            # Detect definitions section
            if level is not None:
                lower = text.lower()
                if "definition" in lower or "defined term" in lower:
                    in_definitions_section = True
                    continue
                elif in_definitions_section and level <= 2:
                    in_definitions_section = False
                    continue

            if not text:
                continue

            # Try to match definition patterns
            for pattern in DEFINITION_PATTERNS:
                m = pattern.match(text)
                if m:
                    term = m.group(1).strip()
                    # Check formatting of the term
                    fmt = self._get_term_formatting(para, term)
                    definitions.append({
                        "term": term,
                        "paragraph_index": idx,
                        "formatting": fmt,
                        "in_section": in_definitions_section,
                    })
                    break

        return definitions

    def _get_term_formatting(self, para, term: str) -> dict:
        """Extract formatting properties of the defined term within the paragraph."""
        for run in para.runs:
            if term in run.text or run.text.strip().strip('"\u201C\u201D') == term:
                return {
                    "bold": resolve_font_property(run, "bold"),
                    "underline": resolve_font_property(run, "underline"),
                    "quoted": any(q in run.text for q in ['"', '\u201C', '\u201D']),
                }
        return {"bold": None, "underline": None, "quoted": False}

    def _check_definition_formatting(
        self, document: Document, definitions: list[dict]
    ) -> list[Finding]:
        """Check that all definitions use consistent formatting."""
        findings = []
        if len(definitions) < 2:
            return findings

        # Count formatting patterns
        formats = defaultdict(int)
        for d in definitions:
            fmt = d["formatting"]
            key = (fmt.get("bold"), fmt.get("quoted"))
            formats[key] += 1

        if len(formats) <= 1:
            return findings

        # Find dominant format
        dominant = max(formats, key=formats.get)

        for d in definitions:
            fmt = d["formatting"]
            key = (fmt.get("bold"), fmt.get("quoted"))
            if key != dominant:
                idx = d["paragraph_index"]
                text = get_full_text(document.paragraphs[idx])[:60]
                dominant_desc = []
                if dominant[0]:
                    dominant_desc.append("bold")
                if dominant[1]:
                    dominant_desc.append("quoted")
                actual_desc = []
                if key[0]:
                    actual_desc.append("bold")
                if key[1]:
                    actual_desc.append("quoted")
                findings.append(
                    Finding(
                        paragraph_index=idx,
                        category=self.category,
                        location=f"Paragraph {idx + 1}: \"{text}...\"",
                        description=(
                            f"Definition of '{d['term']}' has inconsistent formatting: "
                            f"{' + '.join(actual_desc) or 'plain'} vs dominant "
                            f"{' + '.join(dominant_desc) or 'plain'}"
                        ),
                        severity=Severity.MODERATE,
                        fix_data={
                            "term": d["term"],
                            "expected_bold": dominant[0],
                            "expected_quoted": dominant[1],
                        },
                    )
                )

        return findings

    def _check_alphabetical_order(
        self, document: Document, definitions: list[dict]
    ) -> list[Finding]:
        """Check if definitions in the definitions section are alphabetically ordered."""
        findings = []
        section_defs = [d for d in definitions if d.get("in_section")]
        if len(section_defs) < 3:
            return findings

        terms = [d["term"] for d in section_defs]
        sorted_terms = sorted(terms, key=str.lower)

        if terms != sorted_terms:
            # Find the first out-of-order term
            for i, (actual, expected) in enumerate(zip(terms, sorted_terms)):
                if actual != expected:
                    idx = section_defs[i]["paragraph_index"]
                    findings.append(
                        Finding(
                            paragraph_index=idx,
                            category=self.category,
                            location=f"Paragraph {idx + 1}",
                            description=(
                                f"Definitions are not in alphabetical order: "
                                f"'{actual}' should come after '{terms[i-1]}' "
                                f"but expected '{expected}' here"
                            ),
                            severity=Severity.MINOR,
                            fix_data={"type": "alphabetical_order"},
                        )
                    )
                    break  # Report once

        return findings

    def _check_undefined_terms(
        self, document: Document, definitions: list[dict]
    ) -> list[Finding]:
        """Find terms that appear to be defined-term-style but lack definitions."""
        findings = []
        defined_terms = {d["term"].lower() for d in definitions}

        # Collect all quoted capitalized terms used in the document
        term_usage: dict[str, list[int]] = defaultdict(list)
        for idx, para in enumerate(document.paragraphs):
            text = get_full_text(para)
            for m in DEFINED_TERM_USAGE.finditer(text):
                term = m.group(1).strip()
                if term.lower() not in defined_terms and len(term) > 3:
                    term_usage[term].append(idx)

        # Report terms used 3+ times without definition (likely intentional defined terms)
        for term, locations in term_usage.items():
            if len(locations) >= 3:
                idx = locations[0]
                text = get_full_text(document.paragraphs[idx])[:60]
                findings.append(
                    Finding(
                        paragraph_index=idx,
                        category=self.category,
                        location=f"Paragraph {idx + 1}: \"{text}...\"",
                        description=(
                            f"Term '{term}' is used {len(locations)} times in "
                            f"defined-term style but has no definition"
                        ),
                        severity=Severity.MODERATE,
                        fix_data={"type": "undefined_term", "term": term},
                    )
                )

        return findings

    def fix(self, document: Document, finding: Finding, profile: StyleProfile) -> Change:
        # Most definition fixes are flagged for manual review
        # We can auto-fix bold/quote formatting consistency
        fd = finding.fix_data

        if fd.get("term") and fd.get("expected_bold") is not None:
            para = document.paragraphs[finding.paragraph_index]
            term = fd["term"]
            for run in para.runs:
                if term in run.text:
                    if fd.get("expected_bold"):
                        run.font.bold = True
                    break

        return Change(
            change_id=str(uuid.uuid4()),
            category=self.category,
            location=finding.location,
            description=finding.description,
            severity=finding.severity,
            source=ChangeSource.DETERMINISTIC,
        )
