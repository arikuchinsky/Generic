"""Vision finding parser — parses Claude's response into VisionFinding objects."""

from __future__ import annotations

import json
import re

from ...models.enums import Severity
from ...models.schemas import VisionFinding


def parse_vision_response(response_text: str, page_number: int) -> list[VisionFinding]:
    """Parse Claude's vision analysis response into structured findings.

    Handles well-formed JSON and gracefully degrades for slightly malformed output.

    Args:
        response_text: Raw text response from Claude.
        page_number: The page number this analysis corresponds to.

    Returns:
        List of VisionFinding objects.
    """
    findings = []

    # Try JSON extraction first
    json_findings = _extract_json(response_text)
    if json_findings is not None:
        for item in json_findings:
            try:
                finding = _parse_finding_dict(item, page_number)
                if finding:
                    findings.append(finding)
            except Exception:
                continue
        return findings

    # Fallback: regex-based extraction for semi-structured responses
    findings = _regex_fallback_parse(response_text, page_number)
    return findings


def _extract_json(text: str) -> list[dict] | None:
    """Try to extract a JSON array from the response text."""
    # Try the full text as JSON
    try:
        data = json.loads(text.strip())
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in the text (between ``` blocks or bare)
    patterns = [
        re.compile(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```"),
        re.compile(r"(\[[\s\S]*\])"),
    ]

    for pattern in patterns:
        m = pattern.search(text)
        if m:
            try:
                data = json.loads(m.group(1))
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                continue

    return None


def _parse_finding_dict(item: dict, page_number: int) -> VisionFinding | None:
    """Convert a dict from Claude's response to a VisionFinding."""
    if not isinstance(item, dict):
        return None

    severity_str = item.get("severity", "moderate").lower()
    severity_map = {"minor": Severity.MINOR, "moderate": Severity.MODERATE, "major": Severity.MAJOR}
    severity = severity_map.get(severity_str, Severity.MODERATE)

    confidence = item.get("confidence", 0.5)
    if isinstance(confidence, str):
        try:
            confidence = float(confidence)
        except ValueError:
            confidence = 0.5

    return VisionFinding(
        page_number=page_number,
        category=item.get("category", "other"),
        location=item.get("location", f"Page {page_number}"),
        description=item.get("description", ""),
        suggested_fix=item.get("suggested_fix", ""),
        severity=severity,
        confidence=min(max(confidence, 0.0), 1.0),
    )


def _regex_fallback_parse(text: str, page_number: int) -> list[VisionFinding]:
    """Fallback parser using regex for semi-structured responses."""
    findings = []

    # Look for numbered findings like "1. Issue: ..." or "- Issue: ..."
    pattern = re.compile(
        r"(?:^\d+\.|^-)\s*(?:\*\*)?(.+?)(?:\*\*)?\s*[:\-]\s*(.+?)$",
        re.MULTILINE,
    )

    for m in pattern.finditer(text):
        title = m.group(1).strip()
        description = m.group(2).strip()

        # Try to infer category from title
        category = "other"
        title_lower = title.lower()
        if "heading" in title_lower:
            category = "heading_style"
        elif "quote" in title_lower:
            category = "quote_style"
        elif "list" in title_lower or "number" in title_lower:
            category = "list_labels"
        elif "spacing" in title_lower or "alignment" in title_lower:
            category = "paragraph_format"
        elif "reference" in title_lower or "cross" in title_lower:
            category = "cross_references"

        findings.append(
            VisionFinding(
                page_number=page_number,
                category=category,
                location=f"Page {page_number}: {title}",
                description=description,
                severity=Severity.MODERATE,
                confidence=0.5,
            )
        )

    return findings
