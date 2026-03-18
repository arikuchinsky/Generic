"""Smart quote consistency rule.

Detects straight quotes (" and ') and replaces them with typographically
correct smart quotes, using context to determine opening vs closing.
Handles apostrophes in contractions correctly.
"""

from __future__ import annotations

import re
import uuid

from docx import Document

from ....models.enums import ChangeSource, Severity
from ....models.schemas import Change, Example, Finding, StyleProfile
from .base import Rule

# Smart quote characters
OPEN_DOUBLE = "\u201C"   # "
CLOSE_DOUBLE = "\u201D"  # "
OPEN_SINGLE = "\u2018"   # '
CLOSE_SINGLE = "\u2019"  # '

# Common contractions where ' should be a closing (right) single quote
CONTRACTIONS = re.compile(
    r"(?i)\b(can|couldn|didn|doesn|don|hadn|hasn|haven|he|here|how|isn|it|"
    r"let|mightn|mustn|needn|shan|she|shouldn|that|there|they|wasn|we|weren|"
    r"what|when|where|who|won|wouldn|you)'(t|s|d|ll|re|ve|m)\b"
)


class QuoteStyleRule(Rule):
    name = "quote_style"
    category = "quote_style"

    def detect(
        self,
        document: Document,
        profile: StyleProfile,
        config: dict,
        examples: list[Example] | None = None,
    ) -> list[Finding]:
        findings = []
        target = config.get("target", "smart")
        if target != "smart":
            return findings

        for para_idx, para in enumerate(document.paragraphs):
            for run_idx, run in enumerate(para.runs):
                text = run.text
                if not text:
                    continue

                # Detect straight quotes
                has_straight_double = '"' in text
                has_straight_single = "'" in text

                if has_straight_double or has_straight_single:
                    # Count occurrences
                    count = text.count('"') + text.count("'")
                    text_preview = para.text[:60].strip()
                    findings.append(
                        Finding(
                            paragraph_index=para_idx,
                            run_index=run_idx,
                            category=self.category,
                            location=f"Paragraph {para_idx + 1}: \"{text_preview}...\"",
                            description=(
                                f"Found {count} straight quote(s) that should be smart quotes"
                            ),
                            severity=Severity.MINOR,
                            fix_data={"run_idx": run_idx},
                        )
                    )

        return findings

    def fix(self, document: Document, finding: Finding, profile: StyleProfile) -> Change:
        para = document.paragraphs[finding.paragraph_index]
        run = para.runs[finding.run_index]

        original_text = run.text
        new_text = self._convert_to_smart_quotes(
            run.text, finding.paragraph_index, finding.run_index, para
        )
        run.text = new_text

        return Change(
            change_id=str(uuid.uuid4()),
            category=self.category,
            location=finding.location,
            description=f"Converted straight quotes to smart quotes",
            severity=finding.severity,
            source=ChangeSource.DETERMINISTIC,
        )

    def _convert_to_smart_quotes(
        self, text: str, para_idx: int, run_idx: int, para
    ) -> str:
        """Context-aware conversion of straight quotes to smart quotes."""
        result = []
        i = 0

        # Get text before this run for context
        preceding_text = ""
        if run_idx > 0:
            preceding_text = "".join(r.text for r in para.runs[:run_idx])

        while i < len(text):
            ch = text[i]

            if ch == '"':
                # Determine if opening or closing
                before = text[i - 1] if i > 0 else (preceding_text[-1] if preceding_text else "")
                if _is_opening_context(before):
                    result.append(OPEN_DOUBLE)
                else:
                    result.append(CLOSE_DOUBLE)

            elif ch == "'":
                # Check if it's an apostrophe in a contraction
                before = text[:i]
                after = text[i + 1:] if i + 1 < len(text) else ""

                if _is_apostrophe(before, after):
                    # Apostrophes use the closing (right) single quote
                    result.append(CLOSE_SINGLE)
                elif _is_opening_context(text[i - 1] if i > 0 else (
                    preceding_text[-1] if preceding_text else ""
                )):
                    result.append(OPEN_SINGLE)
                else:
                    result.append(CLOSE_SINGLE)
            else:
                result.append(ch)

            i += 1

        return "".join(result)


def _is_opening_context(before_char: str) -> bool:
    """Determine if a quote in this position should be an opening quote."""
    if not before_char:
        return True
    # Opening after whitespace, opening brackets, or start of text
    return before_char in " \t\n\r\u00A0([{—–-/"


def _is_apostrophe(before: str, after: str) -> bool:
    """Determine if a single quote is an apostrophe (vs a quotation mark)."""
    if not before or not after:
        return False
    # Apostrophe if between word characters
    return (
        before and before[-1].isalpha()
        and after and after[0].isalpha()
    )
