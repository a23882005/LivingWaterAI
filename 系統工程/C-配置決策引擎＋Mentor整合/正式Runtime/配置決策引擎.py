"""Public Work5 staging entrypoint for C｜配置決策引擎＋Mentor整合.

Formal implementation lives in work5.core_engine.  This thin entrypoint exists because
C Work5's frozen construction plan explicitly names `配置決策引擎.py`.
"""
from work5.core_engine import (  # noqa: F401
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
