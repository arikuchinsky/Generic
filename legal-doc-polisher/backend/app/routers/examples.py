"""Examples API router — CRUD for learning examples."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from ..learning.store import add_example, delete_example, get_examples
from ..models.schemas import Example, ExampleCreate

router = APIRouter(prefix="/api/examples", tags=["examples"])


@router.get("")
async def list_examples(
    category: str | None = None,
    document_type: str | None = None,
    limit: int = 100,
) -> list[Example]:
    """List learning examples, optionally filtered by category or document type."""
    return await get_examples(category=category, document_type=document_type, limit=limit)


@router.post("")
async def create_example(body: ExampleCreate) -> Example:
    """Create a new learning example."""
    return await add_example(
        category=body.category,
        description=body.description,
        before_context=body.before_context,
        after_context=body.after_context,
        document_type=body.document_type,
        metadata=json.dumps(body.metadata),
    )


@router.delete("/{example_id}")
async def remove_example(example_id: str):
    """Delete a learning example."""
    deleted = await delete_example(example_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Example not found")
    return {"deleted": True}
