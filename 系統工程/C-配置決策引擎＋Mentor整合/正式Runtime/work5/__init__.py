"""C Work5 configuration decision core integration package."""
from .core_engine import (
    WORK5_VERSION,
    ConfigurationEngineValidationError,
    validate_canonical_input,
    run_configuration_engine,
)

__all__ = [
    "WORK5_VERSION",
    "ConfigurationEngineValidationError",
    "validate_canonical_input",
    "run_configuration_engine",
]
