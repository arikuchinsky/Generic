"""Rules API router — read/update formatting rule configuration."""

from __future__ import annotations

import yaml
from fastapi import APIRouter, HTTPException

from ..config import settings

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("")
async def get_rules():
    """Get current rule configuration."""
    if not settings.rules_config_path.exists():
        return {}
    with open(settings.rules_config_path) as f:
        return yaml.safe_load(f) or {}


@router.put("")
async def update_rules(body: dict):
    """Update rule configuration."""
    try:
        with open(settings.rules_config_path, "w") as f:
            yaml.safe_dump(body, f, default_flow_style=False)
        return {"updated": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update rules: {e}")
