"""Polish API router — upload, status, result, download endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import settings
from ..dependencies import get_job, set_job, update_job
from ..engine.orchestrator import polish_document
from ..models.enums import JobStatusEnum
from ..models.schemas import JobStatus, PolishReport, PrePolishOptions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/polish", tags=["polish"])


@router.post("")
async def upload_and_polish(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    options: str = Form("{}"),
):
    """Upload a .docx file and start the polishing process.

    Returns the job_id for status polling.
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")

    # Parse options
    try:
        opts = PrePolishOptions(**json.loads(options))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid options: {e}")

    # Create job
    job_id = str(uuid.uuid4())[:8]
    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded file
    docx_path = job_dir / "original.docx"
    with open(docx_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Initialize job status
    job_status = JobStatus(
        job_id=job_id,
        status=JobStatusEnum.QUEUED,
        progress_pct=0,
        current_step="Queued for processing",
    )
    set_job(job_id, job_status)

    # Start background processing
    background_tasks.add_task(_run_polish_job, job_id, docx_path, opts)

    return {"job_id": job_id}


@router.get("/{job_id}/status")
async def get_job_status(job_id: str):
    """Poll for job status and progress."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/result")
async def get_job_result(job_id: str):
    """Get the full polish report for a completed job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatusEnum.COMPLETE:
        raise HTTPException(status_code=400, detail=f"Job is not complete (status: {job.status})")
    if not job.report:
        raise HTTPException(status_code=500, detail="Report not available")
    return job.report


@router.get("/{job_id}/download")
async def download_polished(job_id: str):
    """Download the polished .docx file."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatusEnum.COMPLETE:
        raise HTTPException(status_code=400, detail="Job is not complete")

    polished_path = settings.jobs_dir / job_id / "polished.docx"
    if not polished_path.exists():
        raise HTTPException(status_code=404, detail="Polished file not found")

    original_name = job.report.original_filename if job.report else "document.docx"
    download_name = f"polished_{original_name}"

    return FileResponse(
        path=str(polished_path),
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


async def _run_polish_job(
    job_id: str, docx_path: Path, options: PrePolishOptions
):
    """Background task to run the polishing pipeline."""

    def status_callback(status: JobStatusEnum, step: str, pct: int):
        update_job(job_id, status=status, current_step=step, progress_pct=pct)

    try:
        report = await polish_document(
            job_id=job_id,
            docx_path=docx_path,
            options=options,
            status_callback=status_callback,
        )
        update_job(
            job_id,
            status=JobStatusEnum.COMPLETE,
            current_step="Polishing complete!",
            progress_pct=100,
            report=report,
        )
    except Exception as e:
        logger.exception(f"Job {job_id} failed: {e}")
        update_job(
            job_id,
            status=JobStatusEnum.ERROR,
            current_step=f"Error: {str(e)[:200]}",
            error_message=str(e),
        )
