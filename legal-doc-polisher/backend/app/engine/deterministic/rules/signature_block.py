"""Signature block formatting rule for CRE legal documents.

Common issues:
- Inconsistent spacing between signature lines
- Misaligned signature blocks (some left, some center)
- Missing or inconsistent underlines for signature lines
- Inconsistent "By:", "Name:", "Title:", "Date:" formatting
- Tab vs space alignment issues in signature blocks
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict

from docx import Document

from ....models.enums import ChangeSource, Severity
from ....models.schemas import Change, Example, Finding, StyleProfile
from ....utils.docx_helpers import (
    alignment_to_str,
    get_full_text,
    resolve_font_property,
    resolve_paragraph_property,
)
from .base import Rule

# Patterns that indicate we're in a signature block area
SIGNATURE_INDICATORS = re.compile(
    r"(?:IN WITNESS WHEREOF|EXECUTED|AGREED AND ACCEPTED|"
    r"SIGNATURE PAGE|COUNTERPART|WITNESS|ACKNOWLEDGED)",
    re.IGNORECASE,
)

# Signature line field patterns
SIGNATURE_FIELD_PATTERNS = [
    re.compile(r"^(By:\s*)", re.IGNORECASE),
    re.compile(r"^(Name:\s*)", re.IGNORECASE),
    re.compile(r"^(Title:\s*)", re.IGNORECASE),
    re.compile(r"^(Date:\s*)", re.IGNORECASE),
    re.compile(r"^(Its:\s*)", re.IGNORECASE),
    re.compile(r"^(Printed Name:\s*)", re.IGNORECASE),
    re.compile(r"^(Authorized Signatory:\s*)", re.IGNORECASE),
]

# Underscore line for signature
SIGNATURE_LINE = re.compile(r"^[_\s]{10,}$")


class SignatureBlockRule(Rule):
    name = "signature_block"
    category = "signature_block"

    def detect(
        self,
        document: Document,
        profile: StyleProfile,
        config: dict,
        examples: list[Example] | None = None,
    ) -> list[Finding]:
        findings = []

        # Find signature block regions
        sig_blocks = self._find_signature_blocks(document)
        if not sig_blocks:
            return findings

        # Check consistency across all signature blocks
        findings.extend(self._check_field_formatting(document, sig_blocks))
        findings.extend(self._check_alignment_consistency(document, sig_blocks))
        findings.extend(self._check_spacing_consistency(document, sig_blocks))

        return findings

    def _find_signature_blocks(self, document: Document) -> list[list[int]]:
        """Find ranges of paragraph indices that form signature blocks."""
        blocks = []
        current_block: list[int] = []
        in_sig_area = False

        for idx, para in enumerate(document.paragraphs):
            text = get_full_text(para).strip()

            if SIGNATURE_INDICATORS.search(text):
                in_sig_area = True
                if current_block:
                    blocks.append(current_block)
                current_block = [idx]
                continue

            if in_sig_area:
                if not text:
                    # Empty paragraph might be spacing within sig block
                    if current_block:
                        current_block.append(idx)
                    continue

                is_sig_field = any(p.match(text) for p in SIGNATURE_FIELD_PATTERNS)
                is_sig_line = bool(SIGNATURE_LINE.match(text))

                if is_sig_field or is_sig_line:
                    current_block.append(idx)
                elif len(current_block) > 1:
                    # Might be a company name or other sig block content
                    current_block.append(idx)
                else:
                    if current_block:
                        blocks.append(current_block)
                        current_block = []
                    in_sig_area = False

        if current_block:
            blocks.append(current_block)

        return blocks

    def _check_field_formatting(
        self, document: Document, sig_blocks: list[list[int]]
    ) -> list[Finding]:
        """Check that signature field labels use consistent formatting."""
        findings = []

        # Collect formatting of all "By:", "Name:", etc. labels
        field_formats: dict[str, list[dict]] = defaultdict(list)

        for block in sig_blocks:
            for idx in block:
                para = document.paragraphs[idx]
                text = get_full_text(para).strip()
                for pattern in SIGNATURE_FIELD_PATTERNS:
                    m = pattern.match(text)
                    if m:
                        label = m.group(1).strip().rstrip(":")
                        fmt = {}
                        if para.runs:
                            run = para.runs[0]
                            fmt["bold"] = resolve_font_property(run, "bold")
                            fmt["font_name"] = resolve_font_property(run, "name")
                        fmt["paragraph_index"] = idx
                        field_formats[label.lower()].append(fmt)
                        break

        # Check consistency within each field type
        for label, formats in field_formats.items():
            if len(formats) < 2:
                continue
            bold_values = [f.get("bold") for f in formats]
            if len(set(v for v in bold_values if v is not None)) > 1:
                # Inconsistent bold
                for f in formats:
                    idx = f["paragraph_index"]
                    text = get_full_text(document.paragraphs[idx])[:60]
                    findings.append(
                        Finding(
                            paragraph_index=idx,
                            category=self.category,
                            location=f"Paragraph {idx + 1}: \"{text}\"",
                            description=(
                                f"Signature field '{label}' has inconsistent bold formatting"
                            ),
                            severity=Severity.MINOR,
                            fix_data={"type": "field_formatting", "label": label},
                        )
                    )
                break  # Report once per field type

        return findings

    def _check_alignment_consistency(
        self, document: Document, sig_blocks: list[list[int]]
    ) -> list[Finding]:
        """Check that all signature blocks share the same alignment."""
        findings = []
        alignments: dict[str, int] = defaultdict(int)
        block_alignments: list[tuple[int, str | None]] = []

        for block in sig_blocks:
            # Use the alignment of the first non-empty paragraph
            for idx in block:
                text = get_full_text(document.paragraphs[idx]).strip()
                if text:
                    align = alignment_to_str(
                        resolve_paragraph_property(document.paragraphs[idx], "alignment")
                    )
                    block_alignments.append((block[0], align))
                    if align:
                        alignments[align] += 1
                    break

        if len(alignments) > 1:
            dominant = max(alignments, key=alignments.get)
            for block_start, align in block_alignments:
                if align and align != dominant:
                    text = get_full_text(document.paragraphs[block_start])[:60]
                    findings.append(
                        Finding(
                            paragraph_index=block_start,
                            category=self.category,
                            location=f"Paragraph {block_start + 1}: \"{text}...\"",
                            description=(
                                f"Signature block alignment '{align}' differs from "
                                f"dominant '{dominant}'"
                            ),
                            severity=Severity.MODERATE,
                            fix_data={
                                "type": "alignment",
                                "expected_alignment": dominant,
                                "block_indices": [block_start],
                            },
                        )
                    )

        return findings

    def _check_spacing_consistency(
        self, document: Document, sig_blocks: list[list[int]]
    ) -> list[Finding]:
        """Check for consistent spacing within and between signature blocks."""
        findings = []

        # Compare space_after for signature field lines
        spacings: list[tuple[int, float | None]] = []

        for block in sig_blocks:
            for idx in block:
                para = document.paragraphs[idx]
                text = get_full_text(para).strip()
                if any(p.match(text) for p in SIGNATURE_FIELD_PATTERNS):
                    sa = resolve_paragraph_property(para, "space_after")
                    sa_pt = sa.pt if sa and hasattr(sa, "pt") else None
                    spacings.append((idx, sa_pt))

        if len(spacings) >= 2:
            vals = [s[1] for s in spacings if s[1] is not None]
            if vals and len(set(vals)) > 1:
                from statistics import mode
                try:
                    expected = mode(vals)
                except Exception:
                    expected = vals[0]
                for idx, val in spacings:
                    if val is not None and abs(val - expected) > 1.0:
                        findings.append(
                            Finding(
                                paragraph_index=idx,
                                category=self.category,
                                location=f"Paragraph {idx + 1}",
                                description=(
                                    f"Signature block spacing inconsistency: "
                                    f"{val}pt vs expected {expected}pt"
                                ),
                                severity=Severity.MINOR,
                                fix_data={
                                    "type": "spacing",
                                    "expected_space_after": expected,
                                },
                            )
                        )

        return findings

    def fix(self, document: Document, finding: Finding, profile: StyleProfile) -> Change:
        fd = finding.fix_data

        if fd.get("type") == "alignment":
            from ....utils.docx_helpers import str_to_alignment
            align = str_to_alignment(fd.get("expected_alignment"))
            if align is not None:
                for idx in fd.get("block_indices", [finding.paragraph_index]):
                    if idx < len(document.paragraphs):
                        document.paragraphs[idx].paragraph_format.alignment = align

        elif fd.get("type") == "spacing":
            from docx.shared import Pt
            para = document.paragraphs[finding.paragraph_index]
            expected = fd.get("expected_space_after")
            if expected is not None:
                para.paragraph_format.space_after = Pt(expected)

        return Change(
            change_id=str(uuid.uuid4()),
            category=self.category,
            location=finding.location,
            description=finding.description,
            severity=finding.severity,
            source=ChangeSource.DETERMINISTIC,
        )
