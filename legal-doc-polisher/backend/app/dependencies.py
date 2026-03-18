"""Shared FastAPI dependencies — in-memory job tracking and shared state."""

from __future__ import annotations

from .models.schemas import JobStatus


# In-memory job store (single user, local app — no need for Redis/Celery)
_jobs: dict[str, JobStatus] = {}


def get_job(job_id: str) -> JobStatus | None:
    return _jobs.get(job_id)


def set_job(job_id: str, status: JobStatus) -> None:
    _jobs[job_id] = status


def update_job(job_id: str, **kwargs) -> None:
    if job_id in _jobs:
        for key, val in kwargs.items():
            setattr(_jobs[job_id], key, val)


def list_jobs() -> list[JobStatus]:
    return list(_jobs.values())
