# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Consistency checks for ArchML models (dangling refs, unused interfaces, etc.)."""

from archml.validation.checks import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
    validate,
)

__all__ = [
    "ValidationError",
    "ValidationResult",
    "ValidationWarning",
    "validate",
]
