"""Pydantic request/response models for the Legal Document Polisher."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .enums import ChangeSource, DocumentType, FocusArea, JobStatusEnum, Severity


# --- Request models ---


class PrePolishOptions(BaseModel):
    document_type: DocumentType = DocumentType.OTHER
    focus_areas: list[FocusArea] = Field(default_factory=list)
    notes: str = ""


# --- Style profile models ---


class FontSpec(BaseModel):
    name: str | None = None
    size_pt: float | None = None
    color: str | None = None


class HeadingStyleSpec(BaseModel):
    bold: bool | None = None
    underline: bool | None = None
    font_name: str | None = None
    font_size_pt: float | None = None
    numbering_format: str | None = None
    alignment: str | None = None


class ListStyleSpec(BaseModel):
    label_format: str | None = None
    indent_pt: float | None = None
    font: FontSpec | None = None


class StyleProfile(BaseModel):
    heading_styles: dict[int, HeadingStyleSpec] = Field(default_factory=dict)
    body_font: FontSpec = Field(default_factory=FontSpec)
    body_alignment: str | None = None
    body_line_spacing: float | None = None
    body_space_before_pt: float | None = None
    body_space_after_pt: float | None = None
    list_styles: dict[str, ListStyleSpec] = Field(default_factory=dict)
    quote_style: Literal["smart", "straight"] = "smart"


# --- Change & report models ---


class Change(BaseModel):
    change_id: str
    category: str
    location: str
    description: str
    severity: Severity = Severity.MINOR
    source: ChangeSource = ChangeSource.DETERMINISTIC


class PolishReport(BaseModel):
    job_id: str
    original_filename: str
    total_changes: int = 0
    changes_by_category: dict[str, int] = Field(default_factory=dict)
    changes: list[Change] = Field(default_factory=list)
    style_profile: StyleProfile = Field(default_factory=StyleProfile)
    processing_time_seconds: float = 0.0
    deterministic_pass_time: float = 0.0
    vision_pass_time: float = 0.0


class JobStatus(BaseModel):
    job_id: str
    status: JobStatusEnum = JobStatusEnum.QUEUED
    progress_pct: int = 0
    current_step: str = "Waiting..."
    report: PolishReport | None = None
    error_message: str | None = None


# --- Finding models (internal) ---


class Finding(BaseModel):
    """A detected formatting issue before it becomes a Change."""

    paragraph_index: int | None = None
    run_index: int | None = None
    category: str = ""
    location: str = ""
    description: str = ""
    severity: Severity = Severity.MINOR
    fix_data: dict = Field(default_factory=dict)


class VisionFinding(BaseModel):
    """A formatting issue detected by the Vision pipeline."""

    page_number: int
    category: str = ""
    location: str = ""
    description: str = ""
    suggested_fix: str = ""
    severity: Severity = Severity.MODERATE
    confidence: float = 0.5


# --- Learning models ---


class Example(BaseModel):
    id: str = ""
    category: str
    description: str
    before_context: str = ""
    after_context: str = ""
    document_type: str = ""
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class ExampleCreate(BaseModel):
    category: str
    description: str
    before_context: str = ""
    after_context: str = ""
    document_type: str = ""
    metadata: dict = Field(default_factory=dict)
