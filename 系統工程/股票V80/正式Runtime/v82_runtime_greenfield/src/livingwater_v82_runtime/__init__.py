"""LivingWaterAI V82 greenfield runtime package."""
from .version import __version__
from .schema_runtime import load_schema, compile_schema, compile_all_schemas
from .validation import (
    ValidatedFundingBinding,
    ValidationIssue,
    V82InputValidationError,
    validate_and_bind_funding,
)
__all__ = [
    "__version__", "load_schema", "compile_schema", "compile_all_schemas",
    "ValidatedFundingBinding", "ValidationIssue", "V82InputValidationError",
    "validate_and_bind_funding",
]

# W7 core rules are intentionally imported by module path to keep package boot side-effect free.
