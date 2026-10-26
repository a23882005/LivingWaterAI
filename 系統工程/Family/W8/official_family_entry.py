"""W8 official Family entry: authenticated B06 Drive DB -> W5 -> handlers.

All resource IDs and account-to-client bindings come from private service
configuration. This module contains no family DB IDs, secrets, market fixtures,
or trade permission. Processing copies of database bytes are short-lived;
Google Drive remains the sole official customer-record store.
"""
import hashlib
import json
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

FAMILY = Path(__file__).resolve().parents[1]
# Names match the existing, approved B06 private resource catalog and policy.
# Never build a resource key from a user-supplied alias or request payload.
RESOURCE_BY_ACCOUNT = {
    "MOU": "family.mou",
    "JO": "family.joseph",
    "AR": "family.arthur",
    "LI": "family.lilian",
}



def _read_existing_w5(db_path, expected_client_id):
    path = FAMILY / "W5" / "family_input.py"
    spec = importlib.util.spec_from_file_location("official_family_w5_reader", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("W5_READER_NOT_FOUND")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_snapshot(db_path, expected_client_id=expected_client_id)


class OfficialFamilyEntry:
    """Operator-bound, real Drive personal resource; always account-scoped."""

    def __init__(self, *, auth, login_account, client_id, coordinator,
                 principal_provider, analysis_provider=None):
        if (not isinstance(login_account, str)
            or login_account not in RESOURCE_BY_ACCOUNT
            or not isinstance(client_id, str) or not client_id.startswith("fam_")
            or not callable(principal_provider)): 
            raise ValueError("OFFICIAL_FAMILY_BINDING_REQUIRED")
        self.auth = auth
        self.login_account = login_account
        self.resource_key = RESOURCE_BY_ACCOUNT[login_account]
        if self.resource_key not in coordinator.headers:
            raise ValueError("OFFICIAL_RESOURCE_BINDING_MISSING")
        self.client_id = client_id
        self.coordinator = coordinator
        self.principal_provider = principal_provider
        self.analysis_provider = analysis_provider

    def _principal(self):
        user = self.auth.require_login()
        if not isinstance(user, str) or user.casefold() != self.login_account.casefold():
            raise PermissionError("FAMILY_PROJECT_ACCOUNT_MISMATCH")
        principal = self.principal_provider()
        subject = getattr(principal, "subject", None)
        if not isinstance(subject, str) or not subject.startswith("account:") or (
            subject.split(":", 1)[1].casefold() != self.login_account.casefold()
        ):
            raise PermissionError("OFFICIAL_DB_PRINCIPAL_MISMATCH")
        # Coordinator performs the durable session revocation/ACL check again.
        return principal

    def current_snapshot(self):
        principal = self._principal()
        # The server-owned B06 resource table binds "personal" to exactly the
        # authorized member's official Google Drive SQLite ID.
        response = self.coordinator.snapshot(self.resource_key, principal)
        raw, sha = response.get("data"), response.get("sha256")
        if (not isinstance(raw, bytes)
            or not raw.startswith(b"SQLite format 3" + bytes([0]))
            or hashlib.sha256(raw).hexdigest() != sha):
            raise RuntimeError("OFFICIAL_DB_READBACK_MISMATCH")
        with TemporaryDirectory(prefix="family-official-reader-") as folder:
            db = Path(folder) / "current.db"
            db.write_bytes(raw)
            snapshot = _read_existing_w5(db, self.client_id)
        if snapshot.get("source_sha256") != sha or snapshot.get("client_id") != self.client_id:
            raise PermissionError("OFFICIAL_CLIENT_SNAPSHOT_MISMATCH")
        # Project the latest sealed owner-confirmed post-trade quantities,
        # including explicit zero closures. The original W1 history remains
        # immutable and available separately for provenance/auditing.
        projection_path = Path(__file__).with_name("post_trade_state.py")
        projection_spec = importlib.util.spec_from_file_location(
            "family_post_trade_state", projection_path)
        if projection_spec is None or projection_spec.loader is None:
            raise RuntimeError("POST_TRADE_MODULE_MISSING")
        projection = importlib.util.module_from_spec(projection_spec)
        projection_spec.loader.exec_module(projection)
        DOMAIN, effective_positions = projection.DOMAIN, projection.effective_positions
        tables = snapshot["tables"]
        if any(x.get("domain_code") == DOMAIN for x in tables.get("portfolio_snapshot_item", [])):
            from copy import deepcopy
            snapshot = deepcopy(snapshot)
            before = snapshot["payload_digest"]
            snapshot["position_history"] = snapshot["tables"]["portfolio_position"]
            snapshot["tables"]["portfolio_position"] = effective_positions(snapshot["tables"])
            snapshot["historical_payload_digest"] = before
            snapshot["payload_digest"] = hashlib.sha256(json.dumps(
                snapshot["tables"], ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            snapshot["position_projection"] = "W8_POST_TRADE_CURRENT_V1"
        return snapshot

    def read_portfolio(self, payload):
        # No caller-supplied Drive ID, db_path or client ID is accepted.
        if not isinstance(payload, dict):
            raise ValueError("INVALID_OFFICIAL_INPUT")
        if any(x in payload for x in ("db_path", "file_id", "client_id", "source_db")):
            raise PermissionError("CALLER_RESOURCE_OVERRIDE_REJECTED")
        snapshot = self.current_snapshot()
        return {"status": "OK", "data_provenance": "SOURCE_BACKED",
                "source_sha256": snapshot["source_sha256"],
                "client_id": snapshot["client_id"], "snapshot": snapshot,
                "trade_authorization": "NONE"}

    def deployment_pace(self, payload):
        """Never turn a raw DB filename into an invented V70/V82 decision.

        analysis_provider is the operator-owned W2/W3/market/funding producer,
        not a callback inferred from user text. It returns a prepared trusted
        request and existing FamilyRunner, both bound to the same DB SHA.
        """
        current = self.read_portfolio(payload)
        missing = [
            name for name in ("final_target_allocation", "cash_balance_snapshot",
                              "funding_evaluation")
            if not current["snapshot"]["tables"].get(name)
        ]
        targets = current["snapshot"]["tables"].get("final_target_version", [])
        allocations = current["snapshot"]["tables"].get("final_target_allocation", [])
        # An older confirmed target must not silently replace a newer,
        # confirmed-but-incomplete version of the same target purpose.
        # Consider ALL rows of the latest confirmed version, not merely
        # the accepted subset; otherwise one accepted 100% plus a pending
        # allocation could incorrectly pass.
        latest = {}
        for version in targets:
            if version.get("lifecycle_state") != "CONFIRMED":
                continue
            key, no = version.get("target_key"), version.get("version_no")
            if not isinstance(key, str) or not key or type(no) is not int or no < 1:
                raise ValueError("OFFICIAL_CONFIRMED_TARGET_ID_INVALID")
            if key not in latest or no > latest[key]["version_no"]:
                latest[key] = version
        valid = []
        for version in latest.values():
            if version.get("completeness_state") != "COMPLETE":
                continue
            weights = [a for a in allocations
                       if a.get("target_key") == version["target_key"]
                       and a.get("version_no") == version["version_no"]]
            instruments = [a.get("instrument_key") for a in weights]
            if (weights and len(instruments) == len(set(instruments))
                    and all(isinstance(k, str) and k for k in instruments)
                    and all(a.get("allocation_state") == "ACCEPTED"
                            and type(a.get("weight_units")) is int
                            and a["weight_units"] > 0 for a in weights)
                    and sum(a["weight_units"] for a in weights) == 1000000):
                valid.append(version)
        if not valid:
            missing.append("confirmed_final_target_version")
        elif len(valid) != 1:
            # No caller-controlled target selector: the W5 trusted source
            # should determine scope, never guess among independent purposes.
            missing.append("single_confirmed_target_purpose")
        if self.analysis_provider is None or missing:
            if self.analysis_provider is None:
                missing.append("official_market_and_approved_engine_request")
            return {"status": "DATA_UNAVAILABLE", "code": "OFFICIAL_ANALYSIS_INPUT_INCOMPLETE",
                    "data_provenance": "SOURCE_BACKED",
                    "client_id": self.client_id,
                    "source_sha256": current["source_sha256"],
                    "missing": missing,
                    "message": "已讀取本人正式持倉；將依已確認的目標、資金與最新市場來源補齊引擎計算所需欄位。",
                    "trade_authorization": "NONE"}
        request, runner = self.analysis_provider(current["snapshot"], dict(payload))
        if (not isinstance(request, dict)
            or request.get("client_id") != self.client_id
            or request.get("client_snapshot", {}).get("payload", {}).get("source_sha256") != current["source_sha256"]):
            raise PermissionError("OFFICIAL_ANALYSIS_SOURCE_MISMATCH")
        context = runner.context_provider()
        if (context.get("client_id") != self.client_id
            or context.get("native_binding", {}).get("data_provenance") != "SOURCE_BACKED"):
            raise PermissionError("OFFICIAL_ANALYSIS_PROVENANCE_REQUIRED")
        decision = runner.analyze(request)
        if decision.get("status") != "OK":
            return {"status": "DATA_UNAVAILABLE", "code": "UPSTREAM_ANALYSIS_INCOMPLETE",
                    "client_id": self.client_id, "source_sha256": current["source_sha256"],
                    "issue_codes": decision.get("issue_codes", []),
                    "trade_authorization": "NONE"}
        if decision.get("client_id") != self.client_id or decision.get("data_provenance") != "SOURCE_BACKED":
            raise PermissionError("OFFICIAL_RESULT_CLIENT_MISMATCH")
        # Preserve upstream HOLD and action semantics. Do not relabel staging
        # or promote calculation to a live authorized investment execution.
        return {"status": "OK", "client_id": self.client_id,
                "source_sha256": current["source_sha256"],
                "data_provenance": "SOURCE_BACKED",
                "analysis": decision, "trade_authorization": "NONE"}

    def handlers(self):
        return {"read_portfolio": self.read_portfolio,
                "deployment_pace": self.deployment_pace}


def build_official_family_menu(*, auth, project_name, login_account, client_id,
                               coordinator, principal_provider, analysis_provider=None,
                               other_handlers=None, completion_checks=None, report_store=None, report_renderer=None,
                               trusted_analysis_source_producer=None,
                               trusted_w6_current_input_producer=None, approved_w6_renderer=None,
                               approved_w6_archive=None):
    """Wire official 02/04 handlers into the existing fourteen-item W7 menu."""
    path = FAMILY / "W7" / "family_menu.py"
    spec = importlib.util.spec_from_file_location("official_family_menu", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("FAMILY_MENU_NOT_FOUND")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if trusted_analysis_source_producer is not None:
        if analysis_provider is not None:
            raise ValueError("CONFLICTING_ANALYSIS_PROVIDERS")
        provider_path = Path(__file__).with_name("on_demand_analysis.py")
        provider_spec = importlib.util.spec_from_file_location(
            "family_w8_on_demand_analysis", provider_path)
        if provider_spec is None or provider_spec.loader is None:
            raise RuntimeError("ON_DEMAND_ANALYSIS_PROVIDER_MISSING")
        provider_module = importlib.util.module_from_spec(provider_spec)
        provider_spec.loader.exec_module(provider_module)
        analysis_provider = provider_module.OnDemandAnalysisProvider(
            trusted_analysis_source_producer)
    official = OfficialFamilyEntry(
        auth=auth, login_account=login_account, client_id=client_id,
        coordinator=coordinator, principal_provider=principal_provider,
        analysis_provider=analysis_provider)
    handlers = dict(other_handlers or {})
    if (trusted_w6_current_input_producer is not None
            or approved_w6_renderer is not None or approved_w6_archive is not None):
        if report_renderer is not None:
            raise ValueError("CONFLICTING_REPORT_RENDERERS")
        if (trusted_w6_current_input_producer is None
                or (approved_w6_renderer is None and approved_w6_archive is None)
                or (approved_w6_renderer is not None and approved_w6_archive is not None)):
            raise ValueError("W6_TRUSTED_PRODUCER_AND_APPROVED_RENDERER_REQUIRED")
        path = Path(__file__).with_name("on_demand_w6.py")
        spec = importlib.util.spec_from_file_location(
            "family_w8_on_demand_w6", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("ON_DEMAND_W6_RENDERER_MODULE_MISSING")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report_renderer = module.OnDemandW6Renderer(
            trusted_w6_current_input_producer, approved_w6_renderer,
            approved_w6_archive=approved_w6_archive)
    if report_renderer is not None and report_store is None:
        raise ValueError('OFFICIAL_REPORT_STORE_REQUIRED')
    if report_store is not None:
        # Report destinations are bound to the same authenticated member and
        # canonical client as the portfolio. Never trust an arbitrary folder.
        if (report_store.login_account != login_account
                or report_store.client_id != client_id):
            raise PermissionError('OFFICIAL_REPORT_OWNER_MISMATCH')
        checked_renderer = None
        if report_renderer is not None:
            def checked_renderer(payload):
                if not isinstance(payload, dict) or any(
                    key in payload for key in ("client_id", "file_id", "db_path", "source_db")
                ):
                    raise PermissionError("REPORT_SOURCE_OVERRIDE_REJECTED")
                snapshot = official.current_snapshot()
                source_path = FAMILY / "W8" / "formal_report_source.py"
                source_spec = importlib.util.spec_from_file_location(
                    "family_w8_formal_report_source", source_path)
                if source_spec is None or source_spec.loader is None:
                    raise RuntimeError("OFFICIAL_REPORT_SOURCE_NOT_FOUND")
                source_module = importlib.util.module_from_spec(source_spec)
                source_spec.loader.exec_module(source_module)
                source = source_module.build_report_source(
                    snapshot, account=login_account, expected_client_id=client_id)
                output = report_renderer(source, dict(payload))
                if (not isinstance(output, dict)
                    or output.get("client_id") != client_id
                    or output.get("source_digest") != source["digest"]
                    or output.get("source_db_sha256") != snapshot["source_sha256"]):
                    raise PermissionError("REPORT_OUTPUT_SOURCE_MISMATCH")
                return output
        handlers.update(module.report_handlers(auth, report_store, renderer=checked_renderer))
    # Reserved operations always use the official resource, not external caller
    # supplied handlers. Other options remain under existing operator routing.
    handlers.update(official.handlers())
    return module.FamilyMenu(
        auth, project_name=project_name, login_account=login_account,
        handlers=handlers, completion_checks=completion_checks)


def handle_stock_question(menu, question):
    """Natural language 'AVGO/博通週一能否加碼' enters official menu 04."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("INVESTMENT_QUESTION_REQUIRED")
    text = question.strip()
    # Transactions are separate from analysis: do not record an execution
    # merely because the person asks whether to buy or add to a position.
    if any(term in text for term in ("加碼", "買點", "投入速度", "能買", "該買",
                                    "何時買", "是否買", "買入時機", "進場")):
        return menu.select(4, payload={"question": text})
    raise ValueError("INVESTMENT_INTENT_NOT_MATCHED")
