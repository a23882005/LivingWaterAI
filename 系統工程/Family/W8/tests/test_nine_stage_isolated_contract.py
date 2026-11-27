"""Collect the isolated candidate acceptance suite in existing PR59 CI.

These are synthetic candidate tests. Importing them here does not register a
candidate profile with the financial runtime or change the deployment default.
"""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[4]
TOOLS=ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/tools'
sys.path.insert(0,str(TOOLS))
from nine_stage_candidate.tests.test_candidate import *  # noqa: F401,F403
