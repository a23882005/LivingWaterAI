"""Authenticated ChatGPT on-demand entry to approved W5 native FamilyRunner.

This binds a trusted, source-backed upstream request to the current official
Google Drive SQLite snapshot and then calls existing V70/V82/bond-V75/Mentor
through W5. No permanent host, guessed market inputs or trading permissions.

The upstream producer is invoked by the active ChatGPT request and supplies
the already validated W2/W3/C7/native bundle. It is never accepted from an
untrusted user request or substituted with historical/fictional numbers.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]
W5_DIR = Path(__file__).resolve().parents[1] / "W5"


def _iso(value):
    if not isinstance(value, str):
        raise ValueError("ON_DEMAND_TIMESTAMP_REQUIRED")
    try:
        out = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("ON_DEMAND_TIMESTAMP_INVALID") from None
    if out.utcoffset() is None:
        raise ValueError("ON_DEMAND_TIMESTAMP_UNZONED")
    return out.astimezone(timezone.utc)


class OnDemandAnalysisProvider:
    """Prepare one deterministic run without making up missing market context."""

    def __init__(self, trusted_source_producer, *,
                 repo_root=PROJECT_ROOT, runner_factory=None):
        if not callable(trusted_source_producer):
            raise ValueError("TRUSTED_W2_W3_PRODUCER_REQUIRED")
        self.producer = trusted_source_producer
        self.repo_root = Path(repo_root)
        self.runner_factory = runner_factory

    def __call__(self, snapshot, payload):
        if (not isinstance(snapshot, dict)
                or snapshot.get("schema_version") != "Family.W5.W1Snapshot.v1"
                or not re.fullmatch(r"fam_[0-9a-f]{32}",
                                    str(snapshot.get("client_id", "")))
                or not re.fullmatch(r"[0-9a-f]{64}",
                                    str(snapshot.get("source_sha256", "")))):
            raise ValueError("ON_DEMAND_VERIFIED_DB_SNAPSHOT_REQUIRED")
        if not isinstance(payload, dict) or set(payload) - {"question"}:
            raise ValueError("ON_DEMAND_QUESTION_REQUIRED")
        # Selecting the visible menu item "04" is itself a valid request.
        # Use its standard current-holdings question; never fabricate market
        # prices or budgets. Explicit malformed questions remain invalid.
        if not payload:
            question = "請評估我目前持有標的的投入速度"
        else:
            question = payload.get("question")
            if not isinstance(question, str) or not question.strip():
                raise ValueError("ON_DEMAND_QUESTION_REQUIRED")
            question = question.strip()
        # The ChatGPT/operator-bound provider gets the W5 source once for this
        # exact DB version. It cannot pick a different family or a different DB.
        pack = self.producer(deepcopy(snapshot), {"question": question})
        if not isinstance(pack, dict):
            raise ValueError("ON_DEMAND_SOURCE_PACK_REQUIRED")
        request = pack.get("request")
        context = pack.get("trusted_context")
        metadata = pack.get("source_metadata")
        if (not isinstance(request, dict)
                or not isinstance(context, dict)
                or not isinstance(metadata, dict)):
            raise ValueError("ON_DEMAND_PACK_INCOMPLETE")
        client = snapshot["client_id"]
        sha = snapshot["source_sha256"]
        req_sha = request.get("client_snapshot", {}).get("payload", {}).get("source_sha256")
        if (request.get("client_id") != client
                or context.get("client_id") != client
                or metadata.get("client_id") != client
                or metadata.get("source_db_sha256") != sha
                or req_sha != sha):
            raise PermissionError("ON_DEMAND_SOURCE_OR_CLIENT_MISMATCH")
        binding = context.get("native_binding", {})
        if (binding.get("schema_version") != "Family.W5.NativeBinding.v1"
                or binding.get("data_provenance") != "SOURCE_BACKED"
                or not binding.get("source_reference")
                or metadata.get("market_data_provenance") != "SOURCE_BACKED"
                or metadata.get("market_verification") is not True):
            raise ValueError("ON_DEMAND_REAL_SOURCES_REQUIRED")
        if (request.get("trade_authorization", "NONE") != "NONE"
                or context.get("trade_authorization", "NONE") != "NONE"):
            raise PermissionError("ON_DEMAND_TRADE_FORBIDDEN")
        run_id=request.get("run_id")
        if not isinstance(run_id, str) or not run_id or metadata.get("run_id") != run_id:
            raise ValueError("ON_DEMAND_RUN_BINDING_REQUIRED")
        latest=_iso(metadata.get("market_as_of"))
        evaluation=_iso(request.get("evaluation_at"))
        if latest > evaluation:
            raise ValueError("ON_DEMAND_FUTURE_MARKET_SOURCE")
        # Individual quote freshness and W2/W3/C7/stock/bond lineage are
        # validated again by the original approved FamilyRunner._validate().
        if self.runner_factory is not None:
            runner = self.runner_factory(self.repo_root, context_provider=lambda: deepcopy(context))
        else:
            path = W5_DIR / "family_runner.py"
            if not path.is_file():
                raise RuntimeError("ON_DEMAND_W5_RUNNER_MISSING")
            if str(W5_DIR) not in sys.path:
                sys.path.insert(0, str(W5_DIR))
            spec = importlib.util.spec_from_file_location("w8_on_demand_family_runner", path)
            if spec is None or spec.loader is None:
                raise RuntimeError("ON_DEMAND_W5_RUNNER_MISSING")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            runner = module.FamilyRunner(self.repo_root,
                                         context_provider=lambda: deepcopy(context))
        return deepcopy(request), runner
