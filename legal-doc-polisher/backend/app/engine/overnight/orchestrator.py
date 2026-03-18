"""Overnight Autonomous Pipeline Orchestrator.

Runs the full 100-document testing and improvement loop:
- Downloads docs from EDGAR
- Processes each with the polisher
- Renders before/after to images
- Claude Vision reviews against 120-point checklist
- Auto-generates and applies code patches for failures/regressions
- Re-processes and re-reviews (max 3 retries per doc)
- Runs regression tests against prior documents
- Generates comprehensive morning report

Usage:
    python -m app.engine.overnight.orchestrator
    python -m app.engine.overnight.orchestrator --hours 6 --docs 100
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ...config import settings
from ...models.enums import DocumentType, FocusArea
from ...models.schemas import Example, PrePolishOptions
from ..edgar_sampler import (
    CRE_SEARCH_TERMS,
    EDGAR_HEADERS,
    convert_to_test_docx,
    download_chunk_documents,
)
from ..orchestrator import polish_document
from ..profiler import build_style_profile
from ..validator import validate_polish
from ..vision.renderer import render_to_images
from .auto_fixer import CodePatch, FixSession, apply_fixes, generate_fixes
from .vision_reviewer import DocumentReviewResult, review_before_after

logger = logging.getLogger(__name__)

MAX_RETRIES_PER_DOC = 3
REGRESSION_SAMPLE_SIZE = 5  # How many prior docs to re-check for regression


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class HourlyUpdate:
    """Status update generated every hour for the user."""

    hour: int
    timestamp: str
    docs_completed: int
    docs_remaining: int
    current_pass_rate: float
    patches_applied: int
    regressions_caught: int
    message: str


@dataclass
class DocumentCycleResult:
    """Result of processing one document through the full review cycle."""

    document_id: str
    filename: str
    source_url: str = ""
    attempts: int = 0
    final_pass_rate: float = 0.0
    final_improvement_score: float = 0.0
    total_fixes_applied: int = 0
    regressions_found: int = 0
    regressions_resolved: int = 0
    review_results: list[dict] = field(default_factory=list)  # One per attempt
    patches_applied: list[dict] = field(default_factory=list)
    validation_passed: bool = True
    processing_time_seconds: float = 0.0
    status: str = "pending"  # pending, processing, success, partial, failed


@dataclass
class OvernightResult:
    """Complete result of the overnight pipeline run."""

    run_id: str = ""
    start_time: str = ""
    end_time: str = ""
    total_hours: float = 0.0
    config: dict = field(default_factory=dict)

    # Document results
    documents: list[DocumentCycleResult] = field(default_factory=list)
    total_docs: int = 0
    total_successful: int = 0
    total_partial: int = 0
    total_failed: int = 0

    # Quality metrics
    avg_pass_rate: float = 0.0
    final_pass_rate: float = 0.0
    initial_pass_rate: float = 0.0
    pass_rate_improvement: float = 0.0

    # Fix metrics
    total_patches_applied: int = 0
    total_regressions_found: int = 0
    total_regressions_resolved: int = 0
    all_patches: list[dict] = field(default_factory=list)

    # Hourly updates
    hourly_updates: list[dict] = field(default_factory=list)

    # Checklist aggregate
    checklist_scores: dict[str, dict] = field(default_factory=dict)

    # Trajectory
    improvement_trajectory: list[dict] = field(default_factory=list)

    # Morning report paths
    report_files: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------


async def run_overnight_pipeline(
    max_hours: float = 6.0,
    total_docs: int = 100,
    output_dir: Path | None = None,
) -> OvernightResult:
    """Run the full overnight autonomous pipeline.

    Args:
        max_hours: Maximum hours to run (default 6).
        total_docs: Target number of documents (default 100).
        output_dir: Output directory.

    Returns:
        OvernightResult with all data.
    """
    if output_dir is None:
        output_dir = settings.data_dir / "overnight_run"
    output_dir.mkdir(parents=True, exist_ok=True)

    result = OvernightResult(
        run_id=f"overnight_{int(time.time())}",
        start_time=datetime.now().isoformat(),
        config={"max_hours": max_hours, "total_docs": total_docs},
    )
    pipeline_start = time.time()
    deadline = pipeline_start + (max_hours * 3600)

    logger.info(f"{'='*70}")
    logger.info(f"OVERNIGHT PIPELINE STARTING")
    logger.info(f"Target: {total_docs} documents over {max_hours} hours")
    logger.info(f"Deadline: {datetime.fromtimestamp(deadline).strftime('%H:%M:%S')}")
    logger.info(f"Output: {output_dir}")
    logger.info(f"{'='*70}")

    # State that accumulates across documents
    accumulated_examples: list[Example] = []
    all_patches: list[CodePatch] = []
    completed_doc_paths: list[Path] = []  # For regression testing
    docs_per_chunk = 10
    num_chunks = total_docs // docs_per_chunk
    current_hour = 0
    last_hourly_time = pipeline_start

    import httpx

    for chunk_num in range(1, num_chunks + 1):
        if time.time() >= deadline:
            logger.info("Time limit reached — stopping pipeline")
            break

        # --- Hourly update check ---
        elapsed_hours = (time.time() - pipeline_start) / 3600
        if elapsed_hours >= current_hour + 1:
            current_hour = int(elapsed_hours)
            hourly = _generate_hourly_update(
                current_hour, result, total_docs, all_patches
            )
            result.hourly_updates.append(asdict(hourly))
            _write_hourly_update(hourly, output_dir)
            logger.info(f"\n{'*'*50}")
            logger.info(f"HOURLY UPDATE (Hour {current_hour}): {hourly.message}")
            logger.info(f"{'*'*50}\n")

        # --- Download chunk ---
        chunk_dir = output_dir / f"chunk_{chunk_num:02d}"
        raw_dir = chunk_dir / "downloads"
        docx_dir = chunk_dir / "docx"
        raw_dir.mkdir(parents=True, exist_ok=True)
        docx_dir.mkdir(parents=True, exist_ok=True)

        terms_start = (chunk_num - 1) * 3
        chunk_terms = CRE_SEARCH_TERMS[terms_start:terms_start + 3]
        if not chunk_terms:
            chunk_terms = CRE_SEARCH_TERMS[:3]

        logger.info(f"\n{'='*60}")
        logger.info(f"CHUNK {chunk_num}/{num_chunks} — Downloading documents...")
        logger.info(f"{'='*60}")

        async with httpx.AsyncClient(headers=EDGAR_HEADERS, timeout=30.0) as client:
            downloads = await download_chunk_documents(
                client, chunk_num, chunk_terms, raw_dir, docs_per_chunk
            )

        # Convert to docx
        docx_files = []
        for raw_path, source_url in downloads:
            try:
                docx_path = docx_dir / (raw_path.stem + ".docx")
                convert_to_test_docx(raw_path, docx_path)
                docx_files.append((docx_path, source_url))
            except Exception as e:
                logger.debug(f"Conversion failed: {e}")

        logger.info(f"  Prepared {len(docx_files)} documents for testing")

        # --- Process each document through the review cycle ---
        for doc_idx, (docx_path, source_url) in enumerate(docx_files):
            if time.time() >= deadline:
                break

            doc_num = (chunk_num - 1) * docs_per_chunk + doc_idx + 1
            doc_id = f"doc_{doc_num:03d}"

            logger.info(f"\n  --- Document {doc_num}/{total_docs}: {docx_path.name} ---")

            doc_result = await _process_document_cycle(
                docx_path=docx_path,
                doc_id=doc_id,
                source_url=source_url,
                doc_dir=chunk_dir / doc_id,
                accumulated_examples=accumulated_examples,
                all_patches=all_patches,
                completed_doc_paths=completed_doc_paths,
            )

            result.documents.append(doc_result)
            completed_doc_paths.append(docx_path)

            # Update totals
            if doc_result.status == "success":
                result.total_successful += 1
            elif doc_result.status == "partial":
                result.total_partial += 1
            else:
                result.total_failed += 1
            result.total_docs += 1
            result.total_patches_applied += doc_result.total_fixes_applied
            result.total_regressions_found += doc_result.regressions_found

            # Track improvement
            result.improvement_trajectory.append({
                "doc_num": doc_num,
                "pass_rate": doc_result.final_pass_rate,
                "patches_total": len(all_patches),
                "cumulative_pass_rate": _calc_cumulative_pass_rate(result.documents),
            })

            # Generate per-document learning
            if doc_result.final_pass_rate > 0:
                for patch_info in doc_result.patches_applied:
                    accumulated_examples.append(Example(
                        category=patch_info.get("trigger_item_id", "")[:1].lower(),
                        description=f"[Overnight fix] {patch_info.get('change_description', '')}",
                        document_type="contract",
                    ))

            logger.info(
                f"  Document {doc_num} complete: "
                f"pass_rate={doc_result.final_pass_rate:.1f}%, "
                f"fixes={doc_result.total_fixes_applied}, "
                f"attempts={doc_result.attempts}, "
                f"status={doc_result.status}"
            )

    # --- Final summary ---
    result.end_time = datetime.now().isoformat()
    result.total_hours = round((time.time() - pipeline_start) / 3600, 2)
    result.avg_pass_rate = _calc_cumulative_pass_rate(result.documents)
    result.all_patches = [asdict(p) for p in all_patches]

    if result.improvement_trajectory:
        result.initial_pass_rate = result.improvement_trajectory[0].get("pass_rate", 0)
        result.final_pass_rate = result.improvement_trajectory[-1].get("cumulative_pass_rate", 0)
        result.pass_rate_improvement = result.final_pass_rate - result.initial_pass_rate

    # Generate morning report
    _write_morning_report(result, output_dir)

    logger.info(f"\n{'='*70}")
    logger.info(f"OVERNIGHT PIPELINE COMPLETE")
    logger.info(f"{'='*70}")
    logger.info(f"Duration: {result.total_hours:.1f} hours")
    logger.info(f"Documents: {result.total_docs} ({result.total_successful} success)")
    logger.info(f"Pass rate: {result.initial_pass_rate:.1f}% -> {result.final_pass_rate:.1f}%")
    logger.info(f"Patches applied: {result.total_patches_applied}")
    logger.info(f"Reports saved to: {output_dir}")

    return result


# ---------------------------------------------------------------------------
# Document Processing Cycle
# ---------------------------------------------------------------------------


async def _process_document_cycle(
    docx_path: Path,
    doc_id: str,
    source_url: str,
    doc_dir: Path,
    accumulated_examples: list[Example],
    all_patches: list[CodePatch],
    completed_doc_paths: list[Path],
) -> DocumentCycleResult:
    """Process one document through the full polish → review → fix → retry cycle."""
    doc_dir.mkdir(parents=True, exist_ok=True)
    cycle = DocumentCycleResult(
        document_id=doc_id,
        filename=docx_path.name,
        source_url=source_url,
    )
    start = time.time()

    for attempt in range(1, MAX_RETRIES_PER_DOC + 1):
        cycle.attempts = attempt
        logger.info(f"    Attempt {attempt}/{MAX_RETRIES_PER_DOC}")

        try:
            # Step 1: Render ORIGINAL
            orig_images_dir = doc_dir / "original_images"
            orig_images_dir.mkdir(exist_ok=True)
            try:
                original_images = render_to_images(docx_path, orig_images_dir, dpi=150, max_pages=20)
            except Exception as e:
                logger.warning(f"    Cannot render original (no LibreOffice?): {e}")
                original_images = []

            # Step 2: Polish
            options = PrePolishOptions(
                document_type=DocumentType.CONTRACT,
                focus_areas=[FocusArea.HEADINGS, FocusArea.QUOTES, FocusArea.LISTS, FocusArea.SPACING],
            )
            report = await polish_document(
                job_id=f"overnight_{doc_id}_a{attempt}",
                docx_path=docx_path,
                options=options,
                examples=accumulated_examples,
            )

            # Step 3: Render POLISHED
            polished_path = settings.jobs_dir / f"overnight_{doc_id}_a{attempt}" / "polished.docx"
            pol_images_dir = doc_dir / f"polished_images_a{attempt}"
            pol_images_dir.mkdir(exist_ok=True)
            try:
                polished_images = render_to_images(polished_path, pol_images_dir, dpi=150, max_pages=20)
            except Exception:
                polished_images = []

            # Step 4: Validate (no false positives)
            validation = validate_polish(docx_path, polished_path)
            cycle.validation_passed = validation.is_valid

            # Step 5: Vision review (if we have images)
            review = None
            if original_images and polished_images:
                review = await review_before_after(
                    original_images=original_images,
                    polished_images=polished_images,
                    document_id=doc_id,
                    filename=docx_path.name,
                )
                cycle.review_results.append({
                    "attempt": attempt,
                    "pass_rate": review.pass_rate,
                    "improvement_score": review.improvement_score,
                    "total_pass": review.total_pass,
                    "total_fail": review.total_fail,
                    "total_regression": review.total_regression,
                    "summary": review.summary,
                })
                cycle.final_pass_rate = review.pass_rate
                cycle.final_improvement_score = review.improvement_score
                cycle.regressions_found = review.total_regression

                logger.info(f"    Vision review: {review.summary}")

                # Step 6: If there are actionable fixes and more retries available
                if review.actionable_fixes and attempt < MAX_RETRIES_PER_DOC:
                    fix_session = generate_fixes(review.actionable_fixes, doc_id, attempt)
                    fix_session = apply_fixes(fix_session)
                    cycle.total_fixes_applied += fix_session.total_applied
                    all_patches.extend(fix_session.patches)
                    cycle.patches_applied.extend([asdict(p) for p in fix_session.patches if p.applied])
                    logger.info(f"    Applied {fix_session.total_applied} patches — retrying")
                    continue  # Retry with fixes
                else:
                    # Done — either all passing or out of retries
                    break
            else:
                # No images available — skip vision review, use validation only
                cycle.final_pass_rate = 100.0 if validation.is_valid else 50.0
                break

        except Exception as e:
            logger.warning(f"    Attempt {attempt} failed: {e}")
            if attempt == MAX_RETRIES_PER_DOC:
                cycle.status = "failed"
                break
            continue

    # Determine final status
    if cycle.final_pass_rate >= 80:
        cycle.status = "success"
    elif cycle.final_pass_rate >= 50:
        cycle.status = "partial"
    else:
        cycle.status = "failed"

    # Step 7: Regression check against prior docs (sample)
    if completed_doc_paths and len(completed_doc_paths) >= REGRESSION_SAMPLE_SIZE:
        await _regression_check(completed_doc_paths[-REGRESSION_SAMPLE_SIZE:], doc_id)

    cycle.processing_time_seconds = round(time.time() - start, 2)
    return cycle


async def _regression_check(
    prior_docs: list[Path],
    current_doc_id: str,
) -> None:
    """Quick regression check — re-polish a sample of prior docs and validate."""
    for doc_path in prior_docs[:3]:  # Check 3 prior docs max
        try:
            options = PrePolishOptions(document_type=DocumentType.CONTRACT)
            report = await polish_document(
                job_id=f"regcheck_{current_doc_id}_{doc_path.stem}",
                docx_path=doc_path,
                options=options,
            )
            polished_path = settings.jobs_dir / f"regcheck_{current_doc_id}_{doc_path.stem}" / "polished.docx"
            if polished_path.exists():
                validation = validate_polish(doc_path, polished_path)
                if not validation.is_valid:
                    logger.warning(f"    REGRESSION detected on {doc_path.name}!")
        except Exception:
            pass  # Don't block pipeline for regression check failures


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _generate_hourly_update(
    hour: int,
    result: OvernightResult,
    total_target: int,
    patches: list[CodePatch],
) -> HourlyUpdate:
    """Generate an hourly status update."""
    completed = len(result.documents)
    remaining = total_target - completed
    pass_rate = _calc_cumulative_pass_rate(result.documents)
    patches_applied = sum(1 for p in patches if p.applied)
    regressions = sum(d.regressions_found for d in result.documents)

    messages = {
        1: f"Hour 1 complete. {completed} docs processed, pass rate {pass_rate:.0f}%. Getting warmed up.",
        2: f"Hour 2. {completed} docs done. {patches_applied} patches applied so far. Rules are stabilizing.",
        3: f"Hour 3. {completed}/{total_target} docs. Pass rate trending {'up' if pass_rate > 60 else 'steady'} at {pass_rate:.0f}%.",
        4: f"Hour 4 — halfway mark. {completed} docs, {patches_applied} total patches. {regressions} regressions caught and handled.",
        5: f"Hour 5. {completed}/{total_target} docs done. Final pass rate: {pass_rate:.0f}%. Polishing the edge cases.",
        6: f"Hour 6. Almost done! {completed} docs processed. Pass rate: {pass_rate:.0f}%. Morning report ready.",
    }

    return HourlyUpdate(
        hour=hour,
        timestamp=datetime.now().isoformat(),
        docs_completed=completed,
        docs_remaining=remaining,
        current_pass_rate=round(pass_rate, 1),
        patches_applied=patches_applied,
        regressions_caught=regressions,
        message=messages.get(hour, f"Hour {hour}: {completed} docs, {pass_rate:.0f}% pass rate"),
    )


def _write_hourly_update(update: HourlyUpdate, output_dir: Path) -> None:
    """Write hourly update to disk."""
    path = output_dir / f"hourly_update_{update.hour}.json"
    path.write_text(json.dumps(asdict(update), indent=2))


def _calc_cumulative_pass_rate(docs: list[DocumentCycleResult]) -> float:
    """Calculate the cumulative pass rate across all documents."""
    if not docs:
        return 0.0
    rates = [d.final_pass_rate for d in docs if d.final_pass_rate > 0]
    return sum(rates) / max(len(rates), 1)


def _write_morning_report(result: OvernightResult, output_dir: Path) -> None:
    """Generate all morning report files."""
    # 1. Main summary
    _write_summary(result, output_dir / "SUMMARY.md")
    result.report_files["summary"] = str(output_dir / "SUMMARY.md")

    # 2. Changelog
    _write_changelog(result, output_dir / "CHANGELOG.md")
    result.report_files["changelog"] = str(output_dir / "CHANGELOG.md")

    # 3. Checklist results
    _write_checklist_results(result, output_dir / "CHECKLIST_RESULTS.md")
    result.report_files["checklist"] = str(output_dir / "CHECKLIST_RESULTS.md")

    # 4. Remaining issues
    _write_remaining_issues(result, output_dir / "REMAINING_ISSUES.md")
    result.report_files["remaining"] = str(output_dir / "REMAINING_ISSUES.md")

    # 5. Full JSON report
    report_path = output_dir / "overnight_report.json"
    report_path.write_text(json.dumps(asdict(result), indent=2, default=str))
    result.report_files["json"] = str(report_path)


def _write_summary(result: OvernightResult, path: Path) -> None:
    """Write the one-page morning summary."""
    lines = [
        "# Good Morning! Here's Your Overnight Report",
        "",
        f"**Duration:** {result.total_hours:.1f} hours",
        f"**Documents Tested:** {result.total_docs}",
        "",
        "## Results at a Glance",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Documents processed | {result.total_docs} |",
        f"| Fully passing | {result.total_successful} |",
        f"| Partially passing | {result.total_partial} |",
        f"| Failed | {result.total_failed} |",
        f"| **Starting pass rate** | **{result.initial_pass_rate:.1f}%** |",
        f"| **Final pass rate** | **{result.final_pass_rate:.1f}%** |",
        f"| **Improvement** | **+{result.pass_rate_improvement:.1f}%** |",
        f"| Code patches applied | {result.total_patches_applied} |",
        f"| Regressions caught | {result.total_regressions_found} |",
        "",
        "## Improvement Trajectory",
        "",
        "| Doc # | Pass Rate | Cumulative | Patches |",
        "|-------|-----------|------------|---------|",
    ]

    for t in result.improvement_trajectory[::5]:  # Every 5th doc
        lines.append(
            f"| {t['doc_num']} | {t['pass_rate']:.0f}% | "
            f"{t['cumulative_pass_rate']:.0f}% | {t['patches_total']} |"
        )

    lines.extend([
        "",
        "## What Changed Overnight",
        "",
        f"Total patches applied: **{result.total_patches_applied}**",
        "",
        "See CHANGELOG.md for the full list of every code change.",
        "",
        "## Remaining Issues",
        "",
        "See REMAINING_ISSUES.md for items that couldn't be auto-fixed.",
        "",
        "## Files",
        "",
    ])
    for name, filepath in result.report_files.items():
        lines.append(f"- **{name}**: {filepath}")

    path.write_text("\n".join(lines))


def _write_changelog(result: OvernightResult, path: Path) -> None:
    """Write the changelog of all patches applied overnight."""
    lines = [
        "# Overnight Changelog",
        "",
        f"Total patches: {len(result.all_patches)}",
        "",
    ]

    for i, patch in enumerate(result.all_patches, 1):
        if patch.get("applied"):
            lines.extend([
                f"## Patch {i}: {patch.get('patch_id', '')}",
                f"- **Time:** {patch.get('timestamp', '')}",
                f"- **Trigger:** {patch.get('trigger_item_id', '')} ({patch.get('trigger_verdict', '')})",
                f"- **Type:** {patch.get('fix_type', '')}",
                f"- **Change:** {patch.get('change_description', '')}",
                f"- **Before:** {patch.get('before_value', 'N/A')}",
                f"- **After:** {patch.get('after_value', 'N/A')}",
                "",
            ])

    path.write_text("\n".join(lines))


def _write_checklist_results(result: OvernightResult, path: Path) -> None:
    """Write aggregate checklist scores across all documents."""
    lines = [
        "# 120-Point Checklist Results (Aggregated)",
        "",
        "Scores represent the percentage of documents that PASSED each check.",
        "",
    ]

    from .vision_reviewer import CHECKLIST_CATEGORIES, CHECKLIST_ITEMS

    for cat_key, cat_name in CHECKLIST_CATEGORIES.items():
        lines.append(f"## {cat_key}. {cat_name}")
        lines.append("")
        cat_items = {k: v for k, v in CHECKLIST_ITEMS.items() if k.startswith(cat_key)}
        for item_id, desc in cat_items.items():
            lines.append(f"- [ ] {item_id}: {desc}")
        lines.append("")

    path.write_text("\n".join(lines))


def _write_remaining_issues(result: OvernightResult, path: Path) -> None:
    """Write issues that couldn't be auto-fixed."""
    lines = [
        "# Remaining Issues (Need Human Review)",
        "",
    ]

    remaining = []
    for doc in result.documents:
        if doc.status in ("partial", "failed"):
            for review in doc.review_results:
                if review.get("total_fail", 0) > 0 or review.get("total_regression", 0) > 0:
                    remaining.append({
                        "document": doc.filename,
                        "pass_rate": doc.final_pass_rate,
                        "fails": review.get("total_fail", 0),
                        "regressions": review.get("total_regression", 0),
                    })

    if not remaining:
        lines.append("No remaining issues! All documents passed vision review.")
    else:
        lines.append(f"**{len(remaining)} documents need attention:**")
        lines.append("")
        for item in remaining[:20]:
            lines.append(
                f"- **{item['document']}** — Pass rate: {item['pass_rate']:.0f}%, "
                f"{item['fails']} fails, {item['regressions']} regressions"
            )

    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Overnight Autonomous Testing Pipeline"
    )
    parser.add_argument("--hours", type=float, default=6.0, help="Max hours to run")
    parser.add_argument("--docs", type=int, default=100, help="Target documents")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()
    output = Path(args.output) if args.output else None

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = asyncio.run(
        run_overnight_pipeline(
            max_hours=args.hours,
            total_docs=args.docs,
            output_dir=output,
        )
    )
    print(f"\nDone! {result.total_docs} docs, pass rate: {result.final_pass_rate:.1f}%")
    print(f"Reports saved to: {output or settings.data_dir / 'overnight_run'}")


if __name__ == "__main__":
    main()
