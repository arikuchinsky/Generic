"""Auto-Fix Engine — translates vision feedback into rule improvements.

When Claude Vision identifies a FAIL or REGRESSION, this module:
1. Categorizes the issue
2. Maps it to the relevant rule
3. Generates a parameter/threshold adjustment or new detection pattern
4. Applies the fix to the rules config or rule code
5. Logs the change for the morning report
"""

from __future__ import annotations

import json
import logging
import time
import yaml
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from ...config import settings
from .vision_reviewer import CheckItemResult

logger = logging.getLogger(__name__)


@dataclass
class CodePatch:
    """A change made to the polisher in response to vision feedback."""

    patch_id: str
    timestamp: str = ""
    trigger_item_id: str = ""
    trigger_verdict: str = ""
    trigger_description: str = ""
    fix_type: str = ""  # config_change, threshold_adjust, new_pattern, rule_enhancement
    target_file: str = ""
    change_description: str = ""
    before_value: str = ""
    after_value: str = ""
    applied: bool = False
    verified: bool = False


@dataclass
class FixSession:
    """A collection of patches applied for one document's issues."""

    document_id: str
    patches: list[CodePatch] = field(default_factory=list)
    total_attempted: int = 0
    total_applied: int = 0
    total_verified: int = 0


# ---------------------------------------------------------------------------
# Fix Strategies
# ---------------------------------------------------------------------------

# Maps checklist item prefixes to fix strategies
ITEM_TO_STRATEGY = {
    "A": "heading_rule_adjust",
    "B": "paragraph_rule_adjust",
    "C": "quote_rule_adjust",
    "D": "list_rule_adjust",
    "E": "crossref_rule_adjust",
    "F": "definition_rule_adjust",
    "G": "header_footer_rule_adjust",
    "H": "signature_rule_adjust",
    "I": "exhibit_rule_adjust",
    "J": "template_detection_adjust",
    "K": "visual_quality_adjust",
}


def generate_fixes(
    actionable_items: list[dict],
    document_id: str,
    iteration: int = 0,
) -> FixSession:
    """Generate code patches from vision feedback.

    Args:
        actionable_items: List of failed/regression items with fix suggestions.
        document_id: Which document triggered this.
        iteration: Retry iteration number.

    Returns:
        FixSession with all generated patches.
    """
    session = FixSession(document_id=document_id)

    for item in actionable_items:
        item_id = item.get("item_id", "")
        category = item_id[0] if item_id else ""
        strategy = ITEM_TO_STRATEGY.get(category, "generic_adjust")

        patch = _generate_patch(item, strategy, iteration)
        if patch:
            session.patches.append(patch)
            session.total_attempted += 1

    return session


def apply_fixes(session: FixSession) -> FixSession:
    """Apply all patches in a fix session.

    Currently handles:
    - Rules config threshold adjustments
    - Adding new detection patterns to the config
    - Adjusting tolerance values

    Returns the session with applied status updated.
    """
    config_path = settings.rules_config_path

    for patch in session.patches:
        try:
            if patch.fix_type == "config_change":
                _apply_config_change(patch, config_path)
                patch.applied = True
                session.total_applied += 1
            elif patch.fix_type == "threshold_adjust":
                _apply_threshold_adjustment(patch, config_path)
                patch.applied = True
                session.total_applied += 1
            elif patch.fix_type == "new_pattern":
                _apply_new_pattern(patch, config_path)
                patch.applied = True
                session.total_applied += 1
            elif patch.fix_type == "tolerance_adjust":
                _apply_tolerance_adjustment(patch, config_path)
                patch.applied = True
                session.total_applied += 1
            else:
                # Log as a recommendation for manual fix
                logger.info(f"  Patch {patch.patch_id} requires manual intervention: {patch.change_description}")
                patch.applied = False
        except Exception as e:
            logger.warning(f"  Failed to apply patch {patch.patch_id}: {e}")
            patch.applied = False

    return session


def _generate_patch(
    item: dict, strategy: str, iteration: int
) -> CodePatch | None:
    """Generate a specific patch based on the fix strategy."""
    item_id = item.get("item_id", "")
    verdict = item.get("verdict", "")
    suggestion = item.get("fix_suggestion", "")
    severity = item.get("severity", "minor")
    details = item.get("details", "")

    patch = CodePatch(
        patch_id=f"patch_{item_id}_{iteration}",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        trigger_item_id=item_id,
        trigger_verdict=verdict,
        trigger_description=item.get("description", ""),
    )

    if strategy == "heading_rule_adjust":
        if "font" in details.lower():
            patch.fix_type = "config_change"
            patch.target_file = "rules_config/default_rules.yaml"
            patch.change_description = f"Ensure heading_style rule checks font_name for item {item_id}"
            if "font_name" not in _get_rule_config("heading_style").get("properties_to_check", []):
                patch.before_value = "properties_to_check without font_name"
                patch.after_value = "properties_to_check with font_name"
                return patch
        elif "spacing" in details.lower() or "space" in details.lower():
            patch.fix_type = "tolerance_adjust"
            patch.target_file = "rules_config/default_rules.yaml"
            patch.change_description = f"Tighten heading spacing tolerance for item {item_id}"
            return patch
        elif "bold" in details.lower() or "underline" in details.lower():
            patch.fix_type = "config_change"
            patch.target_file = "rules_config/default_rules.yaml"
            patch.change_description = f"Ensure heading bold/underline check enabled for {item_id}"
            return patch
        # Default: lower the majority threshold to catch more deviations
        patch.fix_type = "threshold_adjust"
        patch.target_file = "rules_config/default_rules.yaml"
        patch.change_description = f"Lower heading majority_threshold to catch more deviations ({item_id})"
        patch.before_value = "0.75"
        patch.after_value = "0.65"
        return patch

    elif strategy == "paragraph_rule_adjust":
        if "alignment" in details.lower():
            patch.fix_type = "config_change"
            patch.target_file = "rules_config/default_rules.yaml"
            patch.change_description = f"Ensure alignment check is in paragraph_format properties ({item_id})"
            return patch
        elif "spacing" in details.lower():
            patch.fix_type = "tolerance_adjust"
            patch.target_file = "rules_config/default_rules.yaml"
            patch.change_description = f"Reduce spacing tolerance to {0.5}pt ({item_id})"
            patch.before_value = "1.0"
            patch.after_value = "0.5"
            return patch
        patch.fix_type = "threshold_adjust"
        patch.target_file = "rules_config/default_rules.yaml"
        patch.change_description = f"Lower paragraph majority_threshold ({item_id})"
        patch.before_value = "0.80"
        patch.after_value = "0.70"
        return patch

    elif strategy == "quote_rule_adjust":
        patch.fix_type = "config_change"
        patch.target_file = "rules_config/default_rules.yaml"
        patch.change_description = f"Confirm quote_style target=smart and enabled ({item_id})"
        return patch

    elif strategy == "list_rule_adjust":
        patch.fix_type = "config_change"
        patch.target_file = "rules_config/default_rules.yaml"
        patch.change_description = f"Enable all list_labels sub-checks ({item_id})"
        return patch

    elif strategy == "crossref_rule_adjust":
        patch.fix_type = "config_change"
        patch.target_file = "rules_config/default_rules.yaml"
        patch.change_description = f"Ensure cross_references rule is enabled ({item_id})"
        return patch

    elif strategy == "header_footer_rule_adjust":
        patch.fix_type = "config_change"
        patch.target_file = "rules_config/default_rules.yaml"
        patch.change_description = f"Ensure header_footer rule is enabled ({item_id})"
        return patch

    elif strategy == "signature_rule_adjust":
        patch.fix_type = "config_change"
        patch.target_file = "rules_config/default_rules.yaml"
        patch.change_description = f"Ensure signature_block rule is enabled ({item_id})"
        return patch

    elif verdict == "regression":
        # Regressions need more conservative fixes
        patch.fix_type = "threshold_adjust"
        patch.target_file = "rules_config/default_rules.yaml"
        patch.change_description = (
            f"REGRESSION FIX: Increase threshold to be more conservative ({item_id}). "
            f"Details: {details[:200]}"
        )
        return patch

    # Generic fallback
    if suggestion:
        patch.fix_type = "new_pattern"
        patch.change_description = f"Vision suggestion for {item_id}: {suggestion[:300]}"
        return patch

    return None


def _get_rule_config(rule_name: str) -> dict:
    """Load a specific rule's config from the YAML file."""
    config_path = settings.rules_config_path
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}
    return config.get("rules", {}).get(rule_name, {})


def _apply_config_change(patch: CodePatch, config_path: Path) -> None:
    """Apply a configuration change to the rules YAML."""
    if not config_path.exists():
        return

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    rules = config.get("rules", {})
    item_category = patch.trigger_item_id[0] if patch.trigger_item_id else ""

    # Map category to rule name
    cat_to_rule = {
        "A": "heading_style", "B": "paragraph_format", "C": "quote_style",
        "D": "list_labels", "E": "cross_references", "F": "definition_format",
        "G": "header_footer", "H": "signature_block", "I": "signature_block",
        "J": "cross_references", "K": "paragraph_format",
    }
    rule_name = cat_to_rule.get(item_category, "")
    if rule_name and rule_name in rules:
        rules[rule_name]["enabled"] = True

    # Ensure properties_to_check includes all needed properties
    if rule_name == "heading_style":
        props = rules.get(rule_name, {}).get("properties_to_check", [])
        for p in ["bold", "underline", "font_name", "font_size", "alignment"]:
            if p not in props:
                props.append(p)
        rules.setdefault(rule_name, {})["properties_to_check"] = props

    config["rules"] = rules
    with open(config_path, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False)

    logger.info(f"  Applied config change: {patch.change_description}")


def _apply_threshold_adjustment(patch: CodePatch, config_path: Path) -> None:
    """Adjust a threshold value in the rules config."""
    if not config_path.exists():
        return

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    rules = config.get("rules", {})

    # Determine which rule to adjust
    item_category = patch.trigger_item_id[0] if patch.trigger_item_id else ""
    is_regression = patch.trigger_verdict == "regression"

    if item_category == "A":
        current = rules.get("heading_style", {}).get("majority_threshold", 0.75)
        # For regressions, increase threshold (be more conservative)
        # For fails, decrease threshold (catch more deviations)
        if is_regression:
            new_val = min(current + 0.05, 0.90)
        else:
            new_val = max(current - 0.05, 0.50)
        rules.setdefault("heading_style", {})["majority_threshold"] = round(new_val, 2)
        patch.before_value = str(current)
        patch.after_value = str(round(new_val, 2))

    elif item_category == "B":
        current = rules.get("paragraph_format", {}).get("majority_threshold", 0.80)
        if is_regression:
            new_val = min(current + 0.05, 0.95)
        else:
            new_val = max(current - 0.05, 0.55)
        rules.setdefault("paragraph_format", {})["majority_threshold"] = round(new_val, 2)
        patch.before_value = str(current)
        patch.after_value = str(round(new_val, 2))

    config["rules"] = rules
    with open(config_path, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False)

    logger.info(f"  Applied threshold adjustment: {patch.before_value} -> {patch.after_value}")


def _apply_tolerance_adjustment(patch: CodePatch, config_path: Path) -> None:
    """Adjust a tolerance value (e.g., spacing_pt)."""
    if not config_path.exists():
        return

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    rules = config.get("rules", {})

    # Tighten spacing tolerance
    current = rules.get("paragraph_format", {}).get("tolerance", {}).get("spacing_pt", 1.0)
    new_val = max(current - 0.25, 0.25)
    rules.setdefault("paragraph_format", {}).setdefault("tolerance", {})["spacing_pt"] = round(new_val, 2)

    patch.before_value = str(current)
    patch.after_value = str(round(new_val, 2))

    config["rules"] = rules
    with open(config_path, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False)

    logger.info(f"  Applied tolerance adjustment: {patch.before_value} -> {patch.after_value}")


def _apply_new_pattern(patch: CodePatch, config_path: Path) -> None:
    """Add a new detection pattern or enable a disabled rule."""
    # For now, ensure all rules are enabled
    _apply_config_change(patch, config_path)
