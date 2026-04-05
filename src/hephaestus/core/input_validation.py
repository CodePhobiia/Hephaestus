"""Input validation for pipeline entry points."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of input validation."""

    valid: bool
    cleaned: str
    warnings: list[str]
    errors: list[str]


_MIN_PROBLEM_LENGTH = 10
_MAX_PROBLEM_LENGTH = 5000
_SUSPICIOUS_PATTERNS = [
    (r"<script", "Input contains HTML script tags"),
    (r"(?i)ignore\s+(?:previous|above|all)\s+instructions", "Input looks like a prompt injection"),
    (r"\{\{.*\}\}", "Input contains template variables"),
]


def validate_problem(text: str) -> ValidationResult:
    """Validate a problem description for the pipeline.

    Checks length, content quality, and suspicious patterns.
    """
    warnings: list[str] = []
    errors: list[str] = []
    cleaned = text.strip()

    if not cleaned:
        return ValidationResult(valid=False, cleaned="", warnings=[], errors=["Problem is empty."])

    if len(cleaned) < _MIN_PROBLEM_LENGTH:
        errors.append(
            f"Problem is too short ({len(cleaned)} chars). Minimum: {_MIN_PROBLEM_LENGTH}."
        )

    if len(cleaned) > _MAX_PROBLEM_LENGTH:
        warnings.append(
            f"Problem is very long ({len(cleaned)} chars). Consider trimming to key points."
        )
        cleaned = cleaned[:_MAX_PROBLEM_LENGTH]

    # Check for suspicious patterns
    for pattern, message in _SUSPICIOUS_PATTERNS:
        if re.search(pattern, cleaned):
            warnings.append(message)

    # Quality checks
    word_count = len(cleaned.split())
    if word_count < 3:
        warnings.append("Problem has very few words. More detail produces better results.")

    if cleaned.isupper():
        warnings.append("Problem is all uppercase. Consider using normal case.")
        cleaned = cleaned.capitalize()

    return ValidationResult(
        valid=len(errors) == 0,
        cleaned=cleaned,
        warnings=warnings,
        errors=errors,
    )


def validate_domain_hint(domain: str) -> ValidationResult:
    """Validate a domain hint string."""
    cleaned = domain.strip().lower()
    warnings: list[str] = []
    errors: list[str] = []

    if not cleaned:
        return ValidationResult(valid=True, cleaned="", warnings=[], errors=[])

    if len(cleaned) > 100:
        errors.append("Domain hint is too long.")

    if not re.match(r"^[a-z0-9\s_-]+$", cleaned):
        warnings.append("Domain hint contains unusual characters.")

    return ValidationResult(
        valid=len(errors) == 0, cleaned=cleaned, warnings=warnings, errors=errors
    )


__all__ = ["ValidationResult", "validate_problem", "validate_domain_hint"]
