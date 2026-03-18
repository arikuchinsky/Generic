"""Orchestrator — coordinates the full document polishing pipeline.

Sequences: Profile → Deterministic Pass → Render → Vision Pass → Apply Fixes → Report.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Callable

import yaml
from docx import Document

from ..config import settings
from ..models.enums import ChangeSource, JobStatusEnum
from ..models.schemas import (
    Change,
    Example,
    JobStatus,
    PolishReport,
    PrePolishOptions,
    StyleProfile,
)
from .deterministic.runner import run_deterministic_pass
from .profiler import build_style_profile
from .vision.analyzer import analyze_pages
from .vision.fixer import apply_vision_fixes
from .vision.renderer import render_to_images

logger = logging.getLogger(__name__)


async def polish_document(
    job_id: str,
    docx_path: Path,
    options: PrePolishOptions,
    status_callback: Callable[[JobStatusEnum, str, int], None] | None = None,
    examples: list[Example] | None = None,
) -> PolishReport:
    """Run the full polishing pipeline on a document.

    Args:
        job_id: Unique job identifier.
        docx_path: Path to the input .docx file.
        options: User-selected polish options.
        status_callback: Optional callback for status updates (status, step_name, progress_pct).
        examples: Optional learned examples to enhance processing.

    Returns:
        PolishReport with all changes and metadata.
    """
    start_time = time.time()
    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    all_changes: list[Change] = []

    def update_status(status: JobStatusEnum, step: str, pct: int):
        if status_callback:
            status_callback(status, step, pct)

    # --- Step 1: Profile the document ---
    update_status(JobStatusEnum.PROFILING, "Analyzing document styles...", 5)
    logger.info(f"Job {job_id}: Profiling document")

    profile = build_style_profile(docx_path)
    update_status(JobStatusEnum.PROFILING, "Style profile built", 15)

    # --- Step 2: Load rules config ---
    rules_config = _load_rules_config()

    # --- Step 3: Deterministic pass ---
    update_status(JobStatusEnum.DETERMINISTIC_PASS, "Running formatting rules...", 20)
    logger.info(f"Job {job_id}: Starting deterministic pass")
    det_start = time.time()

    document = Document(str(docx_path))
    document, det_changes = run_deterministic_pass(
        document, profile, rules_config, examples
    )
    all_changes.extend(det_changes)
    det_time = time.time() - det_start

    # Save intermediate result
    intermediate_path = job_dir / "after_deterministic.docx"
    document.save(str(intermediate_path))
    update_status(JobStatusEnum.DETERMINISTIC_PASS, f"Found {len(det_changes)} issues", 40)
    logger.info(f"Job {job_id}: Deterministic pass found {len(det_changes)} issues in {det_time:.1f}s")

    # --- Step 4: Vision pass (if enabled) ---
    vision_time = 0.0
    if settings.vision_enabled and settings.anthropic_api_key:
        try:
            # Render to images
            update_status(JobStatusEnum.RENDERING, "Rendering document pages...", 45)
            logger.info(f"Job {job_id}: Rendering pages")
            image_paths = render_to_images(
                intermediate_path, job_dir, max_pages=settings.max_pages_for_vision
            )
            update_status(JobStatusEnum.RENDERING, f"Rendered {len(image_paths)} pages", 55)

            # Vision analysis
            update_status(JobStatusEnum.VISION_PASS, "AI vision analysis in progress...", 60)
            logger.info(f"Job {job_id}: Starting vision pass")
            vision_start = time.time()

            vision_findings = await analyze_pages(
                image_paths, profile, options, examples
            )
            vision_time = time.time() - vision_start

            update_status(
                JobStatusEnum.VISION_PASS,
                f"Vision found {len(vision_findings)} additional issues",
                80,
            )

            # Apply vision fixes
            update_status(JobStatusEnum.APPLYING_FIXES, "Applying vision-detected fixes...", 85)

            # Re-open the document for vision fixes
            document = Document(str(intermediate_path))
            vision_changes = apply_vision_fixes(document, vision_findings, profile)
            all_changes.extend(vision_changes)

            logger.info(
                f"Job {job_id}: Vision pass found {len(vision_findings)} issues, "
                f"produced {len(vision_changes)} changes in {vision_time:.1f}s"
            )

        except Exception as e:
            logger.error(f"Job {job_id}: Vision pass failed: {e}")
            # Continue without vision — deterministic results are still valid

    # --- Step 5: Save final document ---
    update_status(JobStatusEnum.APPLYING_FIXES, "Saving polished document...", 90)
    polished_path = job_dir / "polished.docx"
    document.save(str(polished_path))

    # --- Step 5b: Validate — ensure we didn't introduce new issues ---
    try:
        from .validator import validate_polish
        validation = validate_polish(docx_path, polished_path)
        if not validation.is_valid:
            logger.warning(
                f"Job {job_id}: Validation found {len(validation.issues)} issues. "
                f"Content preserved: {validation.content_preserved}, "
                f"Structure preserved: {validation.structure_preserved}, "
                f"Headers preserved: {validation.headers_preserved}, "
                f"Exhibits preserved: {validation.exhibits_preserved}"
            )
            # If critical issues, fall back to a less-aggressive polish
            critical = [i for i in validation.issues if i.severity == "critical"]
            if critical:
                logger.error(f"Job {job_id}: Critical validation failures — reverting to original")
                # Copy original as polished to avoid corruption
                import shutil
                shutil.copy2(str(docx_path), str(polished_path))
                all_changes = []  # Clear changes since we reverted
    except Exception as e:
        logger.warning(f"Job {job_id}: Validation check failed: {e}")

    # --- Step 6: Build report ---
    total_time = time.time() - start_time
    category_counts = Counter(c.category for c in all_changes)

    report = PolishReport(
        job_id=job_id,
        original_filename=docx_path.name,
        total_changes=len(all_changes),
        changes_by_category=dict(category_counts),
        changes=all_changes,
        style_profile=profile,
        processing_time_seconds=round(total_time, 2),
        deterministic_pass_time=round(det_time, 2),
        vision_pass_time=round(vision_time, 2),
    )

    update_status(JobStatusEnum.COMPLETE, "Polishing complete!", 100)
    logger.info(
        f"Job {job_id}: Complete — {len(all_changes)} total changes in {total_time:.1f}s"
    )

    return report


def _load_rules_config() -> dict:
    """Load the rules configuration from YAML."""
    config_path = settings.rules_config_path
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}
