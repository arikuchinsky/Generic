from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
import uuid


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # "user" | "assistant"
    content: str = ""
    tool_uses: list[dict[str, Any]] = []
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New Chat"
    messages: list[Message] = []
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    working_directory: str = ""
    claude_session_id: Optional[str] = None


class StreamEvent(BaseModel):
    type: str
    data: dict[str, Any] = {}
