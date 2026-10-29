"""W8 04: never run investment engines on an unconfirmed draft target."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
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
            "allocation_state": "ACCEPTED", "instrument_key": "VT", "weight_units": weight}


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
    def test_original_configuration_review_survives_menu_boundary_without_full_mentor_claim(self):
        request={'client_id':CLIENT,'run_id':'r1','evaluation_at':'2026-10-29T10:00:00Z',
            'owner':{'account':'A'},'client_snapshot':{'payload':{'source_sha256':'digest'}}}
        review={'schema_version':'Family.W5.ConfigurationReview.v1','client_id':CLIENT,
            'run_id':'r1','evaluation_at':request['evaluation_at'],'owner':request['owner'],
            'source_db_sha256':'digest','drift_snapshot':{'value_state':'KNOWN','items':[]},
            'full_native_pipeline_complete':False,'full_native_mentor_reached':False,
            'trade_action':'NO_TRADE'}
        class Runner:
            def context_provider(self):
                return {'client_id':CLIENT,'native_binding':{'data_provenance':'SOURCE_BACKED'}}
            def analyze(self,request):
                return {'status':'DATA_UNAVAILABLE','issue_codes':[{'code':'C7_FRAMEWORK_NOT_READY'}],
                    'configuration_review':review}
        obj=entry([version()],[allocation()],lambda *_:(request,Runner()))
        result=obj.deployment_pace({})
        self.assertEqual(result['configuration_review'],review)
        self.assertIsNot(result['configuration_review'],review)
        self.assertIsNone(result['mentor']);self.assertIsNone(result['canonical_result'])
        for key,value in [('client_id','OTHER'),('run_id','OTHER'),('source_db_sha256','OTHER'),
                          ('full_native_mentor_reached',True)]:
            before=deepcopy(review);review[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(PermissionError,'CONFIGURATION_REVIEW_BINDING'):
                obj.deployment_pace({})
            review.clear();review.update(before)

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
                        "data_provenance": "SOURCE_BACKED", "output": "verified",
                        "run_id":"r1","evaluation_at":"2026-10-27T00:00:00Z"}
        def provider(snapshot, payload):
            return ({"client_id": CLIENT,
                     "run_id":"r1","evaluation_at":"2026-10-27T00:00:00Z",
                     "client_snapshot": {"payload": {"source_sha256": "digest"}}},
                    Runner())
        result = entry([version()], [allocation()], provider).deployment_pace({})
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["analysis"]["output"], "verified")
        self.assertEqual(result["analysis"]["source_db_sha256"],"digest")
        self.assertEqual(result["trade_authorization"], "NONE")

    def test_latest_confirmed_incomplete_cannot_reuse_old_target(self):
        versions=[version(), dict(version(),version_no=2)]
        rows=[allocation(), dict(allocation(),version_no=2,weight_units=500000)]
        result=entry(versions,rows).deployment_pace({})
        self.assertIn("confirmed_final_target_version",result["missing"])

    def test_pending_rows_cannot_be_ignored_because_accepted_sum_is_one(self):
        rows=[allocation(), dict(allocation(),instrument_key="QQQ",
                                 weight_units=100000,allocation_state="PENDING")]
        result=entry([version()],rows).deployment_pace({})
        self.assertIn("confirmed_final_target_version",result["missing"])

    def test_multiple_confirmed_target_purposes_do_not_pick_arbitrarily(self):
        versions=[version(),dict(version(),target_key="RETIREMENT")]
        rows=[allocation(),dict(allocation(),target_key="RETIREMENT")]
        result=entry(versions,rows).deployment_pace({})
        self.assertIn("single_confirmed_target_purpose",result["missing"])

    def test_newer_draft_does_not_override_confirmed_target(self):
        versions=[version(),dict(version("DRAFT"),version_no=2)]
        result=entry(versions,[allocation()]).deployment_pace({})
        self.assertNotIn("confirmed_final_target_version",result["missing"])

    def test_confirmed_target_still_needs_provider(self):
        result = entry([version()], [allocation()]).deployment_pace({})
        self.assertEqual(result["status"], "DATA_UNAVAILABLE")
        self.assertNotIn("confirmed_final_target_version", result["missing"])
        self.assertIn("official_market_and_approved_engine_request", result["missing"])

    def test_missing_native_request_still_returns_bound_current_inputs(self):
        obj=entry([version()],[allocation()])
        obj.current_source_provider=lambda snapshot:{'client_id':CLIENT,'source_db_sha256':'digest',
            'status':'SOURCE_INPUTS_READ','v70':{'status':'V70_DATA_READY'},
            'monetary_tactical_amounts':None,'full_native_bundle_ready':False}
        out=obj.deployment_pace({})
        self.assertEqual(out['status'],'DATA_UNAVAILABLE')
        self.assertEqual(out['current_source_inputs']['v70']['status'],'V70_DATA_READY')
        self.assertIsNone(out['current_source_inputs']['monetary_tactical_amounts'])
        obj.current_source_provider=lambda snapshot:{'client_id':CLIENT,'source_db_sha256':'digest','v70':None}
        self.assertEqual(obj.deployment_pace({})['status'],'DATA_UNAVAILABLE')
        obj.current_source_provider=lambda snapshot:{'client_id':'fam_'+'b'*32,'source_db_sha256':'digest'}
        with self.assertRaisesRegex(PermissionError,'OFFICIAL_CURRENT_SOURCE_MISMATCH'):
            obj.deployment_pace({})

    def test_analysis_result_feeds_existing_w6_data_builder(self):
        # Reproduce the actual 04 -> W6 boundary; no hand-added DB hash.
        spec=importlib.util.spec_from_file_location('w6_lineage_fixture',
            ROOT/'tests/test_w6_current_data.py')
        fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
        source,market,engine=fixture.baseline()
        upstream={k:v for k,v in engine.items() if k!='source_db_sha256'}
        class Runner:
            def context_provider(self):
                return {'client_id':CLIENT,'native_binding':{'data_provenance':'SOURCE_BACKED'}}
            def analyze(self,request):return upstream
        request={'client_id':CLIENT,'run_id':engine['run_id'],
                 'evaluation_at':engine['evaluation_at'],
                 'client_snapshot':{'payload':{'source_sha256':fixture.SHA}}}
        obj=entry([version()],[allocation()],lambda *args:(request,Runner()))
        base=obj.read_portfolio({});base['source_sha256']=fixture.SHA
        obj.read_portfolio=lambda _:base
        result=obj.deployment_pace({})
        current=fixture.M.build_w6_current_data(source,market,result['analysis'])
        self.assertEqual(current['current_total_twd'],'2100')
        self.assertEqual(current['run_id'],engine['run_id'])
        self.assertNotIn('source_db_sha256',upstream)
        for patch,code in [({'source_db_sha256':'0'*64},'OFFICIAL_RESULT_SOURCE_MISMATCH'),
                           ({'run_id':'another-run'},'OFFICIAL_RESULT_RUN_MISMATCH'),
                           ({'evaluation_at':'2026-10-01T00:00:00Z'},'OFFICIAL_RESULT_RUN_MISMATCH')]:
            original=dict(upstream);upstream.update(patch)
            with self.subTest(patch=patch),self.assertRaisesRegex(PermissionError,code):
                obj.deployment_pace({})
            upstream.clear();upstream.update(original)


if __name__ == "__main__":
    unittest.main()
