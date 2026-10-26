"""W8 04 trusted on-demand W5 adapter contract: entirely synthetic inputs."""
import importlib.util
from pathlib import Path
import unittest
from copy import deepcopy

PATH = Path(__file__).resolve().parents[1] / "on_demand_analysis.py"
SPEC = importlib.util.spec_from_file_location("w8_on_demand_analysis_test", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
CLIENT = "fam_" + "a"*32
SHA = "1"*64

def snapshot():
    return {"schema_version":"Family.W5.W1Snapshot.v1",
            "client_id":CLIENT,"source_sha256":SHA,"tables":{}}

def pack():
    return {
        "request":{"client_id":CLIENT,"run_id":"r001","evaluation_at":"2026-10-26T07:00:00Z",
                   "client_snapshot":{"payload":snapshot()},
                   "trade_authorization":"NONE"},
        "trusted_context":{"client_id":CLIENT,"trade_authorization":"NONE",
                           "native_binding":{"schema_version":"Family.W5.NativeBinding.v1",
                                             "data_provenance":"SOURCE_BACKED",
                                             "source_reference":"approved-source"}},
        "source_metadata":{"client_id":CLIENT,"source_db_sha256":SHA,
                           "market_data_provenance":"SOURCE_BACKED",
                           "market_verification":True,"run_id":"r001",
                           "market_as_of":"2026-10-26T06:00:00Z"},
    }

def runner_factory(root, *, context_provider):
    class Runner:
        def context_provider(self):return context_provider()
        def analyze(self,request):
            return {"status":"OK","client_id":CLIENT,"data_provenance":"SOURCE_BACKED"}
    return Runner()

class OnDemandTests(unittest.TestCase):
    def provider(self, value):
        return MOD.OnDemandAnalysisProvider(lambda snap, req: deepcopy(value),
                                            runner_factory=runner_factory)

    def test_verified_source_reaches_original_runner_contract(self):
        req,runner=self.provider(pack())(snapshot(),{"question":"AVGO是否加碼"})
        self.assertEqual(req["client_id"],CLIENT)
        self.assertEqual(runner.context_provider()["client_id"],CLIENT)
        self.assertEqual(runner.analyze(req)["status"],"OK")

    def test_bare_menu_04_uses_standard_holdings_question(self):
        seen=[]
        def trusted_producer(snapshot, asked):
            seen.append(dict(asked))
            return deepcopy(pack())
        provider=MOD.OnDemandAnalysisProvider(
            trusted_producer, runner_factory=runner_factory)
        request,runner=provider(snapshot(),{})
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0]["question"],
                         "請評估我目前持有標的的投入速度")
        self.assertEqual(runner.analyze(request)["status"],"OK")

    def test_explicit_blank_question_cannot_bypass_validation(self):
        with self.assertRaisesRegex(ValueError,"ON_DEMAND_QUESTION_REQUIRED"):
            self.provider(pack())(snapshot(),{"question":"  "})

    def test_other_family_rejected(self):
        p=pack();p["request"]["client_id"]="fam_"+"b"*32
        with self.assertRaisesRegex(PermissionError,"ON_DEMAND_SOURCE_OR_CLIENT_MISMATCH"):
            self.provider(p)(snapshot(),{"question":"買"})
    
    def test_stale_or_synthetic_unverified_producer_rejected(self):
        p=pack();p["source_metadata"]["market_verification"]=False
        with self.assertRaisesRegex(ValueError,"ON_DEMAND_REAL_SOURCES_REQUIRED"):
            self.provider(p)(snapshot(),{"question":"買"})
        p=pack();p["trusted_context"]["native_binding"]["data_provenance"]="SYNTHETIC"
        with self.assertRaisesRegex(ValueError,"ON_DEMAND_REAL_SOURCES_REQUIRED"):
            self.provider(p)(snapshot(),{"question":"買"})

    def test_future_market_rejected(self):
        p=pack();p["source_metadata"]["market_as_of"]="2026-10-28T06:00:00Z"
        with self.assertRaisesRegex(ValueError,"ON_DEMAND_FUTURE_MARKET_SOURCE"):
            self.provider(p)(snapshot(),{"question":"買"})

    def test_current_sha_cannot_hide_altered_holdings(self):
        p=pack();p["request"]["client_snapshot"]["payload"]["tables"]={
            "portfolio_position":[{"quantity_decimal":"999"}]}
        with self.assertRaisesRegex(PermissionError,"ON_DEMAND_SNAPSHOT_CONTENT_MISMATCH"):
            self.provider(p)(snapshot(),{})

    def test_producer_cannot_mutate_verified_snapshot(self):
        original=snapshot()
        def mutate(snap, question):
            snap["tables"]["portfolio_position"]=[{"quantity_decimal":"999"}]
            p=pack();p["request"]["client_snapshot"]["payload"]=snap
            return p
        provider=MOD.OnDemandAnalysisProvider(mutate,runner_factory=runner_factory)
        with self.assertRaisesRegex(PermissionError,"ON_DEMAND_SNAPSHOT_CONTENT_MISMATCH"):
            provider(original,{})
        self.assertEqual(original,snapshot())

    def test_trade_permission_rejected(self):
        p=pack();p["trusted_context"]["trade_authorization"]="EXECUTE"
        with self.assertRaisesRegex(PermissionError,"ON_DEMAND_TRADE_FORBIDDEN"):
            self.provider(p)(snapshot(),{"question":"買"})

    def test_untrusted_db_override_rejected(self):
        with self.assertRaisesRegex(ValueError,"ON_DEMAND_QUESTION_REQUIRED"):
            self.provider(pack())(snapshot(),{"question":"買","client_id":"fam_other"})

if __name__=="__main__":
    unittest.main()
