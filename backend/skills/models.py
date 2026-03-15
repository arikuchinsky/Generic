from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TranscriptEntry(BaseModel):
    turn: int
    stage: str
    confidence: int = 1  # 1-4
    section: str = ""
    claude_message: str = ""
    user_response: str = ""
    decision: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SkillSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill_id: str
    current_stage: str = ""
    context: dict[str, Any] = {}  # accumulated state
    transcript: list[TranscriptEntry] = []
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    files: dict[str, str] = {}  # key → file path on disk
    pending_revisions: list[dict[str, Any]] = []  # revisions awaiting approval
    approved_revisions: list[dict[str, Any]] = []  # user-approved revisions
    revision_index: int = 0  # which revision we're currently presenting


class SkillResponse(BaseModel):
    """A single message from the skill to the user."""
    type: str = "question"  # question | info | action | complete | revision_approval
    content: str = ""
    confidence: int = 1  # 1=auto, 2=suggest, 3=choose, 4=input
    options: list[str] = []
    stage: str = ""
    metadata: dict[str, Any] = {}
