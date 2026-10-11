"""Read-only JSON Schema runtime for W5.

Schema compilation is allowed in W5. Instance/business validation is exposed as
an API surface but its use as the formal Input Validation engine belongs to W6.
"""
from __future__ import annotations
import json
from importlib.resources import files
from typing import Any, Mapping
from jsonschema import Draft202012Validator

_SCHEMA_FILES = {
    "runtime_input": "runtime_input.schema.json",
    "runtime_output": "runtime_output.schema.json",
}

def load_schema(name: str) -> dict[str, Any]:
    if name not in _SCHEMA_FILES:
        raise KeyError(f"unknown schema: {name}")
    resource = files("livingwater_v82_runtime.schema").joinpath(_SCHEMA_FILES[name])
    return json.loads(resource.read_text(encoding="utf-8"))

def compile_schema(name: str) -> Draft202012Validator:
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)

def compile_all_schemas() -> Mapping[str, Draft202012Validator]:
    return {name: compile_schema(name) for name in _SCHEMA_FILES}
