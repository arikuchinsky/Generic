from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from .models import SkillSession, SkillResponse, TranscriptEntry


class BaseSkill(ABC):
    """Base class for all skills. Each skill defines a multi-stage workflow."""

    id: str
    name: str
    icon: str
    description: str
    stages: list[str]  # ordered stage identifiers

    @abstractmethod
    async def handle_message(
        self,
        session: SkillSession,
        user_input: str,
        uploaded_file: Optional[dict] = None,
    ) -> list[SkillResponse]:
        """Process user input at the current stage. Returns one or more responses."""
        ...

    @abstractmethod
    async def get_stage_prompt(self, session: SkillSession) -> SkillResponse:
        """Get the initial prompt/question for the current stage."""
        ...

    def advance_stage(self, session: SkillSession) -> bool:
        """Move to next stage. Returns False if already at last stage."""
        idx = self.stages.index(session.current_stage)
        if idx < len(self.stages) - 1:
            session.current_stage = self.stages[idx + 1]
            return True
        return False

    def log_transcript(
        self,
        session: SkillSession,
        claude_message: str,
        user_response: str = "",
        confidence: int = 1,
        section: str = "",
        decision: str = "",
    ):
        entry = TranscriptEntry(
            turn=len(session.transcript) + 1,
            stage=session.current_stage,
            confidence=confidence,
            section=section,
            claude_message=claude_message,
            user_response=user_response,
            decision=decision,
            timestamp=datetime.now().isoformat(),
        )
        session.transcript.append(entry)


# Skill registry
_registry: dict[str, BaseSkill] = {}


def register_skill(skill: BaseSkill):
    _registry[skill.id] = skill


def get_skill(skill_id: str) -> Optional[BaseSkill]:
    return _registry.get(skill_id)


def list_skills() -> list[dict[str, str]]:
    return [
        {
            "id": s.id,
            "name": s.name,
            "icon": s.icon,
            "description": s.description,
            "stages": s.stages,
        }
        for s in _registry.values()
    ]
