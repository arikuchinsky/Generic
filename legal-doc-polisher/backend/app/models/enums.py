"""Enumerations for document types and focus areas."""

from enum import Enum


class DocumentType(str, Enum):
    CONTRACT = "contract"
    BRIEF = "brief"
    MEMORANDUM = "memorandum"
    AGREEMENT = "agreement"
    MOTION = "motion"
    PLEADING = "pleading"
    OTHER = "other"


class FocusArea(str, Enum):
    HEADINGS = "headings"
    QUOTES = "quotes"
    LISTS = "lists"
    SPACING = "spacing"


class JobStatusEnum(str, Enum):
    QUEUED = "queued"
    PROFILING = "profiling"
    DETERMINISTIC_PASS = "deterministic_pass"
    RENDERING = "rendering"
    VISION_PASS = "vision_pass"
    APPLYING_FIXES = "applying_fixes"
    COMPLETE = "complete"
    ERROR = "error"


class Severity(str, Enum):
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"


class ChangeSource(str, Enum):
    DETERMINISTIC = "deterministic"
    VISION = "vision"
