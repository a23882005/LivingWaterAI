"""W8 04: never run investment engines on an unconfirmed draft target."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("w8_official_entry_target", ROOT / "official_family_entry.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CLIENT = "fam_" + "a" * 32


def version(state="CONFIRMED"):
    return {"target_key": "MAIN", "version_no": 1,
            "lifecycle_state": state, "completeness_state": "COMPLETE"}


def allocation(weight=1000000):
    return {"target_key": "MAIN", "version_no": 1,
            "allocation_state": "ACCEPTED", "weight_units": weight}


def entry(versions, allocations, provider=None):
    obj = object.__new__(module.OfficialFamilyEntry)
    obj.client_id = CLIENT
    obj.analysis_provider = provider
    obj.read_portfolio = lambda _: {
        "source_sha256": "digest",
        "snapshot": {"tables": {
            "final_target_version": versions,
            "final_target_allocation": allocations,
            "cash_balance_snapshot": [{"account_key": "A"}],
            "funding_evaluation": [{"account_key": "A"}]}}}
    return obj


class TargetReadinessTest(unittest.TestCase):
    def test_draft_target_blocks_engine(self):
        called = []
        obj = entry([version("DRAFT")], [allocation()],
                    lambda *args: called.append(1))
        result = obj.deployment_pace({"question": "何時買"})
        self.assertEqual(result["status"], "DATA_UNAVAILABLE")
        self.assertIn("confirmed_final_target_version", result["missing"])
        self.assertFalse(called)

    def test_incomplete_weight_blocks_engine(self):
        result = entry([version()], [allocation(500000)]).deployment_pace({})
        self.assertIn("confirmed_final_target_version", result["missing"])

    def test_confirmed_target_reaches_trusted_runner(self):
        class Runner:
            def context_provider(self):
                return {"client_id": CLIENT,
                        "native_binding": {"data_provenance": "SOURCE_BACKED"}}
            def analyze(self, request):
                return {"status": "OK", "client_id": CLIENT,
                        "data_provenance": "SOURCE_BACKED", "output": "verified"}
        def provider(snapshot, payload):
            return ({"client_id": CLIENT,
                     "client_snapshot": {"payload": {"source_sha256": "digest"}}},
                    Runner())
        result = entry([version()], [allocation()], provider).deployment_pace({})
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["analysis"]["output"], "verified")
        self.assertEqual(result["trade_authorization"], "NONE")

    def test_confirmed_target_still_needs_provider(self):
        result = entry([version()], [allocation()]).deployment_pace({})
        self.assertEqual(result["status"], "DATA_UNAVAILABLE")
        self.assertNotIn("confirmed_final_target_version", result["missing"])
        self.assertIn("official_market_and_approved_engine_request", result["missing"])


if __name__ == "__main__":
    unittest.main()
