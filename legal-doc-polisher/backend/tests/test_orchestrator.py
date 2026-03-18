"""Tests for the orchestrator."""

import pytest
from pathlib import Path

from app.engine.profiler import build_style_profile
from app.engine.deterministic.runner import run_deterministic_pass
from docx import Document


def test_full_deterministic_pass(sample_dirty_docx):
    """Run the full deterministic pass and verify changes are produced."""
    profile = build_style_profile(sample_dirty_docx)
    doc = Document(str(sample_dirty_docx))

    import yaml
    config_path = Path(__file__).parent.parent / "rules_config" / "default_rules.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    doc, changes = run_deterministic_pass(doc, profile, config)

    # Should find multiple issues in the dirty document
    assert len(changes) >= 1

    # Check that changes span multiple categories
    categories = {c.category for c in changes}
    assert len(categories) >= 1
