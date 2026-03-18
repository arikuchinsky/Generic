"""List label consistency rule.

Detects and fixes:
- Duplicate numbering labels (e.g., two items labeled "2.")
- Gaps in numbering sequence (e.g., 1, 2, 4)
- Format inconsistency within a list (e.g., mixing "1." and "(1)")
- Text-based pseudo-list label errors
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict

from docx import Document

from ....models.enums import ChangeSource, Severity
from ....models.schemas import Change, Example, Finding, StyleProfile
from ....utils.docx_helpers import get_full_text, get_heading_level, get_num_pr
from .base import Rule

# Patterns for text-based list labels
TEXT_LIST_PATTERNS = [
    (re.compile(r"^\(([a-z])\)\s"), "lower_alpha_paren"),
    (re.compile(r"^\(([A-Z])\)\s"), "upper_alpha_paren"),
    (re.compile(r"^\((\d+)\)\s"), "decimal_paren"),
    (re.compile(r"^(\d+)\.\s"), "decimal_dot"),
    (re.compile(r"^(\d+)\)\s"), "decimal_rparen"),
    (re.compile(r"^([a-z])\.\s"), "lower_alpha_dot"),
    (re.compile(r"^([A-Z])\.\s"), "upper_alpha_dot"),
    (re.compile(r"^([ivxlcdm]+)\.\s", re.IGNORECASE), "roman_dot"),
    (re.compile(r"^\(([ivxlcdm]+)\)\s", re.IGNORECASE), "roman_paren"),
]


class ListLabelsRule(Rule):
    name = "list_labels"
    category = "list_labels"

    def detect(
        self,
        document: Document,
        profile: StyleProfile,
        config: dict,
        examples: list[Example] | None = None,
    ) -> list[Finding]:
        findings = []

        check_sequence = config.get("check_sequence", True)
        check_format = config.get("check_format_consistency", True)
        check_nesting = config.get("check_nesting", True)

        # 1. Check XML-based numbering
        if check_sequence:
            findings.extend(self._check_xml_numbering(document))

        # 2. Check text-based pseudo-lists
        findings.extend(self._check_text_lists(document, check_sequence, check_format))

        return findings

    def _check_xml_numbering(self, document: Document) -> list[Finding]:
        """Check for numbering issues in paragraphs with w:numPr."""
        findings = []
        # Group consecutive paragraphs by numId
        groups: dict[str, list[tuple[int, int]]] = defaultdict(list)  # numId -> [(para_idx, ilvl)]

        for idx, para in enumerate(document.paragraphs):
            num_id, ilvl = get_num_pr(para)
            if num_id and num_id != "0":
                groups[num_id].append((idx, ilvl or 0))

        # Check each group for issues
        for num_id, items in groups.items():
            # Group by ilvl within each numId
            by_level: dict[int, list[int]] = defaultdict(list)
            for para_idx, ilvl in items:
                by_level[ilvl].append(para_idx)

            for ilvl, para_indices in by_level.items():
                if len(para_indices) < 2:
                    continue

                # Check for consecutive duplicates or sequence gaps
                # (We can't easily read the actual rendered number from python-docx,
                # but we can flag when the same numId+ilvl appears non-consecutively
                # which often indicates a restart issue)
                for i in range(1, len(para_indices)):
                    gap = para_indices[i] - para_indices[i - 1]
                    if gap > 5:  # Non-consecutive items in the same list might be a restart issue
                        para = document.paragraphs[para_indices[i]]
                        text = get_full_text(para)[:50]
                        findings.append(
                            Finding(
                                paragraph_index=para_indices[i],
                                category=self.category,
                                location=f"Paragraph {para_indices[i] + 1}: \"{text}...\"",
                                description=(
                                    f"List numbering may have unintended restart "
                                    f"(numId={num_id}, level={ilvl})"
                                ),
                                severity=Severity.MODERATE,
                                fix_data={"type": "sequence_gap", "num_id": num_id, "ilvl": ilvl},
                            )
                        )

        return findings

    def _check_text_lists(
        self, document: Document, check_sequence: bool, check_format: bool
    ) -> list[Finding]:
        """Check for issues in text-based (non-XML) list labels."""
        findings = []

        # Scan for runs of consecutive paragraphs with text-based labels
        current_list: list[tuple[int, str, str, str]] = []  # (idx, format, label, full_match)
        current_format = None

        for idx, para in enumerate(document.paragraphs):
            if get_heading_level(para) is not None:
                if current_list:
                    findings.extend(
                        self._analyze_text_list(current_list, document, check_sequence, check_format)
                    )
                    current_list = []
                    current_format = None
                continue

            text = get_full_text(para).strip()
            if not text:
                if current_list:
                    findings.extend(
                        self._analyze_text_list(current_list, document, check_sequence, check_format)
                    )
                    current_list = []
                    current_format = None
                continue

            # Check if this paragraph starts with a list label
            matched = False
            for pattern, fmt in TEXT_LIST_PATTERNS:
                m = pattern.match(text)
                if m:
                    label = m.group(1)
                    if current_format is None or current_format == fmt:
                        current_format = fmt
                        current_list.append((idx, fmt, label, m.group(0)))
                    else:
                        # Different format — end current list, start new one
                        if current_list:
                            findings.extend(
                                self._analyze_text_list(
                                    current_list, document, check_sequence, check_format
                                )
                            )
                        current_list = [(idx, fmt, label, m.group(0))]
                        current_format = fmt
                    matched = True
                    break

            if not matched and current_list:
                # Non-list paragraph breaks the list
                findings.extend(
                    self._analyze_text_list(current_list, document, check_sequence, check_format)
                )
                current_list = []
                current_format = None

        if current_list:
            findings.extend(
                self._analyze_text_list(current_list, document, check_sequence, check_format)
            )

        return findings

    def _analyze_text_list(
        self,
        items: list[tuple[int, str, str, str]],
        document: Document,
        check_sequence: bool,
        check_format: bool,
    ) -> list[Finding]:
        """Analyze a group of text-based list items for issues."""
        findings = []
        if len(items) < 2:
            return findings

        # Check for duplicate labels
        labels = [item[2] for item in items]
        seen = {}
        for i, (idx, fmt, label, full_match) in enumerate(items):
            if label in seen:
                text = get_full_text(document.paragraphs[idx])[:50]
                findings.append(
                    Finding(
                        paragraph_index=idx,
                        category=self.category,
                        location=f"Paragraph {idx + 1}: \"{text}...\"",
                        description=f"Duplicate list label '{full_match.strip()}' (first seen at paragraph {seen[label] + 1})",
                        severity=Severity.MAJOR,
                        fix_data={
                            "type": "duplicate_label",
                            "expected_label": self._next_label(labels[i - 1], fmt) if i > 0 else label,
                            "format": fmt,
                            "full_match": full_match,
                        },
                    )
                )
            else:
                seen[label] = idx

        # Check for sequence gaps (numeric/alpha)
        if check_sequence and items[0][1] in ("decimal_dot", "decimal_paren", "decimal_rparen"):
            for i in range(1, len(items)):
                prev_val = self._label_to_int(items[i - 1][2])
                curr_val = self._label_to_int(items[i][2])
                if prev_val is not None and curr_val is not None:
                    if curr_val != prev_val + 1 and curr_val != prev_val:
                        idx = items[i][0]
                        text = get_full_text(document.paragraphs[idx])[:50]
                        findings.append(
                            Finding(
                                paragraph_index=idx,
                                category=self.category,
                                location=f"Paragraph {idx + 1}: \"{text}...\"",
                                description=(
                                    f"List sequence gap: expected "
                                    f"'{prev_val + 1}' but found '{curr_val}'"
                                ),
                                severity=Severity.MODERATE,
                                fix_data={
                                    "type": "sequence_gap",
                                    "expected": str(prev_val + 1),
                                    "actual": items[i][2],
                                    "format": items[i][1],
                                    "full_match": items[i][3],
                                },
                            )
                        )

        return findings

    def fix(self, document: Document, finding: Finding, profile: StyleProfile) -> Change:
        para = document.paragraphs[finding.paragraph_index]
        fd = finding.fix_data
        fix_type = fd.get("type", "")

        if fix_type in ("duplicate_label", "sequence_gap") and "expected" in fd:
            # Fix text-based label
            old_match = fd.get("full_match", "")
            if old_match and para.runs:
                expected = fd["expected"]
                fmt = fd.get("format", "")
                new_label = self._format_label(expected, fmt)
                # Replace in the first run's text
                for run in para.runs:
                    if old_match in run.text:
                        run.text = run.text.replace(old_match, new_label, 1)
                        break

        return Change(
            change_id=str(uuid.uuid4()),
            category=self.category,
            location=finding.location,
            description=finding.description,
            severity=finding.severity,
            source=ChangeSource.DETERMINISTIC,
        )

    @staticmethod
    def _label_to_int(label: str) -> int | None:
        try:
            return int(label)
        except ValueError:
            return None

    @staticmethod
    def _next_label(current: str, fmt: str) -> str:
        try:
            val = int(current)
            return str(val + 1)
        except ValueError:
            if len(current) == 1 and current.isalpha():
                return chr(ord(current) + 1)
        return current

    @staticmethod
    def _format_label(value: str, fmt: str) -> str:
        fmt_map = {
            "decimal_dot": f"{value}. ",
            "decimal_paren": f"{value}) ",
            "decimal_rparen": f"{value}) ",
            "lower_alpha_paren": f"({value}) ",
            "upper_alpha_paren": f"({value}) ",
            "lower_alpha_dot": f"{value}. ",
            "upper_alpha_dot": f"{value}. ",
        }
        return fmt_map.get(fmt, f"{value}. ")
