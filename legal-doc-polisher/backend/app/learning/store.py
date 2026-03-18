"""SQLite-backed examples store for the learning system."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import aiosqlite

from ..config import settings
from ..models.schemas import Example

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS examples (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    before_context TEXT DEFAULT '',
    after_context TEXT DEFAULT '',
    document_type TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_examples_category ON examples(category);
CREATE INDEX IF NOT EXISTS idx_examples_document_type ON examples(document_type);
"""


async def _get_db() -> aiosqlite.Connection:
    """Get a database connection, creating the schema if needed."""
    db = await aiosqlite.connect(str(settings.db_path))
    db.row_factory = aiosqlite.Row
    await db.executescript(DB_SCHEMA)
    return db


async def add_example(
    category: str,
    description: str,
    before_context: str = "",
    after_context: str = "",
    document_type: str = "",
    metadata: str = "{}",
) -> Example:
    """Add a new learning example."""
    example_id = str(uuid.uuid4())[:8]
    db = await _get_db()
    try:
        await db.execute(
            """INSERT INTO examples (id, category, description, before_context,
               after_context, document_type, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (example_id, category, description, before_context, after_context,
             document_type, metadata),
        )
        await db.commit()
    finally:
        await db.close()

    return Example(
        id=example_id,
        category=category,
        description=description,
        before_context=before_context,
        after_context=after_context,
        document_type=document_type,
        created_at=datetime.now(),
    )


async def get_examples(
    category: str | None = None,
    document_type: str | None = None,
    limit: int = 100,
) -> list[Example]:
    """Retrieve learning examples, optionally filtered."""
    db = await _get_db()
    try:
        query = "SELECT * FROM examples WHERE 1=1"
        params: list = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if document_type:
            query += " AND document_type = ?"
            params.append(document_type)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        return [
            Example(
                id=row["id"],
                category=row["category"],
                description=row["description"],
                before_context=row["before_context"] or "",
                after_context=row["after_context"] or "",
                document_type=row["document_type"] or "",
                created_at=row["created_at"],
            )
            for row in rows
        ]
    finally:
        await db.close()


async def delete_example(example_id: str) -> bool:
    """Delete a learning example by ID."""
    db = await _get_db()
    try:
        cursor = await db.execute("DELETE FROM examples WHERE id = ?", (example_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()
