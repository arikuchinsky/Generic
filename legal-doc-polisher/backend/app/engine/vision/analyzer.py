"""Vision analyzer — sends page images to Claude Vision API for analysis.

This is the core Anthropic API integration for the vision pipeline.
It sends rendered document page images to Claude with structured prompts
and parses the responses into actionable findings.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import anthropic

from ...config import settings
from ...models.schemas import Example, PrePolishOptions, StyleProfile, VisionFinding
from .finding_parser import parse_vision_response
from .prompt_builder import build_vision_prompt

logger = logging.getLogger(__name__)


async def analyze_pages(
    image_paths: list[Path],
    profile: StyleProfile,
    options: PrePolishOptions,
    examples: list[Example] | None = None,
) -> list[VisionFinding]:
    """Analyze document page images using Claude Vision API.

    Pages are processed sequentially for thoroughness — each page's analysis
    can benefit from context about the overall document.

    Args:
        image_paths: Paths to page PNG images, in order.
        profile: The document's inferred style profile.
        options: User-selected polish options.
        examples: Optional learned examples for prompt enrichment.

    Returns:
        List of VisionFinding objects across all pages.
    """
    if not settings.anthropic_api_key:
        logger.warning("No Anthropic API key configured; skipping vision analysis")
        return []

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    all_findings: list[VisionFinding] = []
    total_pages = len(image_paths)

    for page_idx, image_path in enumerate(image_paths):
        page_number = page_idx + 1
        logger.info(f"Analyzing page {page_number}/{total_pages}")

        try:
            findings = await _analyze_single_page(
                client=client,
                image_path=image_path,
                profile=profile,
                options=options,
                examples=examples,
                page_number=page_number,
                total_pages=total_pages,
            )
            all_findings.extend(findings)
        except anthropic.APIError as e:
            logger.error(f"Claude API error on page {page_number}: {e}")
            continue
        except Exception as e:
            logger.error(f"Error analyzing page {page_number}: {e}")
            continue

    return all_findings


async def _analyze_single_page(
    client: anthropic.Anthropic,
    image_path: Path,
    profile: StyleProfile,
    options: PrePolishOptions,
    examples: list[Example] | None,
    page_number: int,
    total_pages: int,
) -> list[VisionFinding]:
    """Analyze a single page image with Claude Vision.

    Args:
        client: Anthropic client instance.
        image_path: Path to the page PNG image.
        profile: Document style profile.
        options: Polish options.
        examples: Optional learned examples.
        page_number: Current page number.
        total_pages: Total page count.

    Returns:
        List of VisionFinding for this page.
    """
    # Read and encode the image
    image_data = image_path.read_bytes()
    base64_image = base64.standard_b64encode(image_data).decode("utf-8")

    # Determine media type from file extension
    suffix = image_path.suffix.lower()
    media_type_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_type_map.get(suffix, "image/png")

    # Build the prompt
    prompt = build_vision_prompt(
        profile=profile,
        options=options,
        examples=examples,
        page_number=page_number,
        total_pages=total_pages,
    )

    # Call Claude Vision API
    message = client.messages.create(
        model=settings.vision_model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    # Extract text response
    response_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            response_text += block.text

    # Parse findings
    findings = parse_vision_response(response_text, page_number)
    logger.info(f"Page {page_number}: found {len(findings)} issues")

    return findings
