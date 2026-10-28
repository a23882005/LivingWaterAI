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


class NativeSourceAssemblyError(ValueError):
    def __init__(self, missing):
        self.missing=tuple(missing)
        super().__init__('NATIVE_SOURCE_INPUTS_REQUIRED:'+','.join(missing))


def assemble_native_input(request, context, native_sources):
    """Assemble original contracts from trusted producer outputs in one pass.

    No fixture/default financial values enter this function. Report all absent
    source sections together, then let the original FamilyRunner validate the
    financial contracts and invoke the original engines.
    """
    bundle_keys=('stock_request','bond_request','stock_evidence','producer_contract',
                 'stock_source_fields','bond_evidence','asset_framework','physical_sgov')
    context_keys=('funding_source','valuation_source','v70_source','c7_source','technical_source')
    sources=deepcopy(native_sources)
    if not isinstance(sources,dict):raise NativeSourceAssemblyError(['native_sources'])
    bundle=sources.get('native_bundle',{})
    source_context=sources.get('trusted_context',{})
    mapping=sources.get('native_binding',{})
    missing=['native_bundle.'+k for k in bundle_keys
             if not isinstance(bundle,dict) or not isinstance(bundle.get(k),dict) or not bundle[k]]
    missing+=['trusted_context.'+k for k in context_keys
              if not isinstance(source_context,dict) or not isinstance(source_context.get(k),dict) or not source_context[k]]
    missing+=['native_binding.'+k for k in ('native_owner','stock_instrument','bond_instruments')
              if not isinstance(mapping,dict) or not isinstance(mapping.get(k),dict) or not mapping[k]]
    if missing:raise NativeSourceAssemblyError(missing)
    if mapping.get('data_provenance')!='SOURCE_BACKED':
        raise ValueError('NATIVE_ASSEMBLY_SOURCE_BACKED_REQUIRED')
    req=deepcopy(request);ctx=deepcopy(context)
    from family_input import digest
    from family_boundary import prepare_input
    ctx.update({k:deepcopy(source_context[k]) for k in context_keys})
    req['native_bundle']={k:deepcopy(bundle[k]) for k in bundle_keys}
    for name in ('valuation','v70','c7','technical'):
        req[name+'_source_digest' if name!='valuation' else 'valuation_digest']=digest(ctx[name+'_source'])
    prepared=prepare_input(req,trusted_context=ctx)
    ctx['native_binding']={**deepcopy(mapping),
        'schema_version':'Family.W5.NativeBinding.v1',
        'family_owner':deepcopy(req['owner']),
        'data_provenance':'SOURCE_BACKED',
        'source_reference':sources.get('source_reference'),
        'bundle_digest':digest(req['native_bundle']),
        'target_binding_digest':prepared.payload['target_binding']['binding_digest'],
        'request_digest':prepared.input_digest}
    if not ctx['native_binding']['source_reference']:
        raise NativeSourceAssemblyError(['source_reference'])
    return req,ctx


class OnDemandAnalysisProvider:
    """Prepare one deterministic run without making up missing market context."""

    # External W2/document sources are checked by original FamilyRunner after
    # this provider binds their request to the current official DB snapshot.
    supports_external_target_source = True

    def __init__(self, trusted_source_producer, *,
                 repo_root=PROJECT_ROOT, runner_factory=None,
                 official_holdings_decision=None, official_file_id=None):
        if not callable(trusted_source_producer):
            raise ValueError("TRUSTED_W2_W3_PRODUCER_REQUIRED")
        self.producer = trusted_source_producer
        self.repo_root = Path(repo_root)
        self.runner_factory = runner_factory
        self.official_holdings_decision = deepcopy(official_holdings_decision)
        self.official_file_id = official_file_id
        if official_holdings_decision is not None and not official_file_id:
            raise ValueError('OFFICIAL_HOLDINGS_FILE_ID_REQUIRED')

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
        # Bind the actual data, not just the producer's repeated source SHA.
        # Otherwise a pack can carry stale holdings under the current DB label.
        if request["client_snapshot"]["payload"] != snapshot:
            raise PermissionError("ON_DEMAND_SNAPSHOT_CONTENT_MISMATCH")
        if self.official_holdings_decision is not None:
            proof_spec=importlib.util.spec_from_file_location(
                'family_w8_official_holdings',Path(__file__).with_name('approved_target_input.py'))
            proof_module=importlib.util.module_from_spec(proof_spec)
            proof_spec.loader.exec_module(proof_module)
            context = deepcopy(context)
            context['holdings_completeness'] = proof_module.bind_official_holdings(
                snapshot, official_file_id=self.official_file_id,
                account_key=request['owner']['account'],
                owner_decision=self.official_holdings_decision,
                evaluation_at=request['evaluation_at'])
        if 'analysis_report' in pack:
            if str(W5_DIR) not in sys.path:sys.path.insert(0,str(W5_DIR))
            here=str(Path(__file__).resolve().parent)
            if here not in sys.path:sys.path.insert(0,here)
            from family_input import digest
            from holdings_analysis import HoldingsAnalysisRunner,STATES
            from loop2_cash_scenario import validate_cash_overlay
            report=pack['analysis_report']
            if (report.get('status') not in STATES
                or report.get('client_id')!=client or report.get('run_id')!=request.get('run_id')
                or metadata.get('run_id')!=request.get('run_id')
                or report.get('source_db_sha256')!=sha
                or report.get('request_digest')!=digest(request)
                or request.get('trade_authorization','NONE')!='NONE'
                or context.get('trade_authorization','NONE')!='NONE'):
                raise PermissionError('ON_DEMAND_HOLDINGS_ANALYSIS_BINDING_MISMATCH')
            trial=report['cash_trial'];scenario=trial['scenario']
            validated=validate_cash_overlay(scenario['raw_cash'],scenario,snapshot=snapshot,
                owner=trial['owner'],authorization=scenario['authorization'],run_id=request['run_id'])
            if validated['effective_cash']!=trial['decimal_values']:
                raise PermissionError('ON_DEMAND_CASH_OVERLAY_INVALID')
            # A cash conflict is diagnostic and does not block independent A.
            context=deepcopy(context)
            context['holdings_analysis_binding']={'schema_version':'Family.W8.HoldingsAnalysisBinding.v1',
                'client_id':client,'run_id':request['run_id'],'source_db_sha256':sha,
                'report_digest':report['report_digest'],'source_data_provenance':'SOURCE_BACKED'}
            return deepcopy(request),HoldingsAnalysisRunner(context=context,report=report)
        if 'native_sources' in pack:
            if str(W5_DIR) not in sys.path:sys.path.insert(0,str(W5_DIR))
            request,context=assemble_native_input(request,context,pack['native_sources'])
        source_report=pack.get('source_production')
        if source_report is not None:
            if str(W5_DIR) not in sys.path:sys.path.insert(0,str(W5_DIR))
            from family_input import digest
            from family_runner import FamilyRunner
            if (source_report.get('schema_version')!='Family.W8.NativeSourceProduction.v1'
                or source_report.get('status') not in ('BLOCKED_BY_ORIGINAL_ADAPTER','SOURCE_STAGE_INCOMPLETE')
                or source_report.get('client_id')!=client
                or source_report.get('source_db_sha256')!=sha
                or source_report.get('run_id')!=request.get('run_id')
                or source_report.get('request_digest')!=digest(request)):
                raise PermissionError('ON_DEMAND_SOURCE_FAILURE_BINDING_MISMATCH')
            if source_report.get('mode')=='CASH_ZERO_SIMULATION':
                from loop2_cash_scenario import validate_cash_overlay
                for trial in source_report.get('cash_by_domain',{}).values():
                    scenario=trial['scenario']
                    validated=validate_cash_overlay(scenario['raw_cash'],scenario,
                        snapshot=snapshot,owner=trial['owner'],authorization=scenario['authorization'],
                        run_id=request['run_id'])
                    if validated['issues'] or validated['effective_cash']!=trial['decimal_values']:
                        raise PermissionError('ON_DEMAND_CASH_OVERLAY_INVALID')
            context=deepcopy(context)
            context['source_production_binding']={'schema_version':'Family.W8.SourceProductionBinding.v1',
                'data_provenance':'SOURCE_BACKED','report_digest':source_report['report_digest'],
                'effective_input_provenance':source_report.get('effective_input_provenance'),
                'client_id':client,'source_db_sha256':sha,'run_id':request['run_id']}
            return deepcopy(request),FamilyRunner(self.repo_root,context_provider=lambda:deepcopy(context),
                native_source_report=source_report)
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
