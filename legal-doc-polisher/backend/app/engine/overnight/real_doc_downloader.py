"""Download real legal documents from public GitHub repos for testing.

Sources:
- open-agreements/open-agreements (34 real legal templates)
- meanbee/company-contracts (3 contracts)
- kemitchell/contract-docx (1 contract)
- ShuttleworthFoundation/agreement_templates

Supplements with synthetic docs (with real formatting bugs) to reach 100.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Real docx files from public GitHub repos
GITHUB_DOCX_SOURCES = [
    # open-agreements — 34 real legal templates
    ("open-agreements/open-agreements", "main", [
        "content/external/yc-safe-discount/template.docx",
        "content/external/yc-safe-mfn/template.docx",
        "content/external/yc-safe-pro-rata-side-letter/template.docx",
        "content/external/yc-safe-valuation-cap/template.docx",
        "content/templates/bonterms-mutual-nda/template.docx",
        "content/templates/bonterms-professional-services-agreement/template.docx",
        "content/templates/closing-checklist/template.docx",
        "content/templates/common-paper-ai-addendum-in-app/template.docx",
        "content/templates/common-paper-ai-addendum/template.docx",
        "content/templates/common-paper-amendment/template.docx",
        "content/templates/common-paper-business-associate-agreement/template.docx",
        "content/templates/common-paper-cloud-service-agreement/template.docx",
        "content/templates/common-paper-csa-click-through/template.docx",
        "content/templates/common-paper-csa-with-ai/template.docx",
        "content/templates/common-paper-csa-with-sla/template.docx",
        "content/templates/common-paper-csa-without-sla/template.docx",
        "content/templates/common-paper-data-processing-agreement/template.docx",
        "content/templates/common-paper-design-partner-agreement/template.docx",
        "content/templates/common-paper-independent-contractor-agreement/template.docx",
        "content/templates/common-paper-letter-of-intent/template.docx",
        "content/templates/common-paper-mutual-nda/template.docx",
        "content/templates/common-paper-one-way-nda/template.docx",
        "content/templates/common-paper-order-form-with-sla/template.docx",
        "content/templates/common-paper-order-form/template.docx",
        "content/templates/common-paper-partnership-agreement/template.docx",
        "content/templates/common-paper-pilot-agreement/template.docx",
        "content/templates/common-paper-professional-services-agreement/template.docx",
        "content/templates/common-paper-software-license-agreement/template.docx",
        "content/templates/common-paper-statement-of-work/template.docx",
        "content/templates/common-paper-term-sheet/template.docx",
        "content/templates/openagreements-employee-ip-inventions-assignment/template.docx",
        "content/templates/openagreements-employment-confidentiality-acknowledgement/template.docx",
        "content/templates/openagreements-employment-offer-letter/template.docx",
        "content/templates/working-group-list/template.docx",
    ]),
    # meanbee — employment / maintenance / NDA contracts
    ("meanbee/company-contracts", "master", [
        "docx/EmploymentContract.docx",
        "docx/MaintenanceAgreement.docx",
        "docx/MutualNDA.docx",
    ]),
    # kemitchell — a traditional contract format
    ("kemitchell/contract-docx", "main", [
        "Traditional.docx",
    ]),
]


async def download_real_documents(
    output_dir: Path,
    max_docs: int = 100,
) -> list[tuple[Path, str]]:
    """Download real legal documents from GitHub.

    Args:
        output_dir: Directory to save downloaded .docx files.
        max_docs: Maximum documents to download.

    Returns:
        List of (local_path, source_url) tuples.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[tuple[Path, str]] = []

    headers = {"User-Agent": "LegalDocPolisher/0.1 (overnight-test)"}

    async with httpx.AsyncClient(
        headers=headers,
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        for repo, branch, file_paths in GITHUB_DOCX_SOURCES:
            for file_path in file_paths:
                if len(downloaded) >= max_docs:
                    break

                raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{file_path}"
                local_name = _make_local_name(repo, file_path, len(downloaded) + 1)
                local_path = output_dir / local_name

                try:
                    resp = await client.get(raw_url)
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        local_path.write_bytes(resp.content)
                        downloaded.append((local_path, raw_url))
                        logger.info(f"  Downloaded [{len(downloaded)}]: {local_name}")
                    else:
                        logger.debug(f"  Skipped {raw_url}: status={resp.status_code}, size={len(resp.content)}")
                except Exception as e:
                    logger.debug(f"  Failed {raw_url}: {e}")

                # Rate limit
                await asyncio.sleep(0.2)

    logger.info(f"Downloaded {len(downloaded)} real documents from GitHub")
    return downloaded


async def download_and_supplement(
    output_dir: Path,
    target_count: int = 100,
) -> list[tuple[Path, str]]:
    """Download real docs and supplement with synthetic ones to reach target.

    Args:
        output_dir: Base output directory.
        target_count: Target total document count.

    Returns:
        List of (path, source) tuples for all documents.
    """
    real_dir = output_dir / "real"
    synth_dir = output_dir / "synthetic"

    # Download real docs
    real_docs = await download_real_documents(real_dir, max_docs=target_count)

    # Supplement with synthetic docs if needed
    all_docs = list(real_docs)
    remaining = target_count - len(real_docs)

    if remaining > 0:
        logger.info(f"Generating {remaining} synthetic documents to reach {target_count}")
        from .synthetic_docs import generate_synthetic_document

        for i in range(1, remaining + 1):
            try:
                path, bugs = generate_synthetic_document(
                    doc_number=i,
                    output_dir=synth_dir,
                    seed=i * 42 + 7,
                    bug_density=0.7,
                )
                all_docs.append((path, f"synthetic:{path.name}"))
            except Exception as e:
                logger.debug(f"  Synthetic doc {i} failed: {e}")

    logger.info(f"Total documents prepared: {len(all_docs)} ({len(real_docs)} real, {len(all_docs) - len(real_docs)} synthetic)")
    return all_docs


def _make_local_name(repo: str, file_path: str, index: int) -> str:
    """Generate a clean local filename from repo and path."""
    repo_short = repo.split("/")[-1][:15]
    # Extract meaningful name from path
    parts = file_path.replace("/template.docx", "").replace(".docx", "").split("/")
    name_part = parts[-1] if parts else "doc"
    name_part = name_part.replace(" ", "_")[:40]
    return f"{index:03d}_{repo_short}_{name_part}.docx"
