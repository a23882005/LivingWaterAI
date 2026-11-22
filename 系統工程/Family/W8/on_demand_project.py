"""Family W8 one-shot ChatGPT Project runtime; GitHub program + Drive SQLite.

The ChatGPT executor must obtain the exact user's official Drive DB first.
This adapter provides W7's 14-option menu with a local, read-only equivalent
of the B06 snapshot interface. It never deploys Python to a website, handles
no API credentials and never persists anything by itself. For menu writes,
reuse the separately approved on_demand_drive_io staged/backup/readback flow.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json
import re
import sqlite3


ROOT=Path(__file__).resolve().parent
FAMILY_NAMES={"MOU":"mou","JO":"Joseph","AR":"Arthur","LI":"Lilian"}
RESOURCE_KEYS={"MOU":"family.mou","JO":"family.joseph",
               "AR":"family.arthur","LI":"family.lilian"}


def _load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:
        raise RuntimeError("FAMILY_ON_DEMAND_DEPENDENCY_MISSING")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FamilyLoginAdapter:
    """Use the approved Sources FamilyLogin, adapting W7's two-arg login API."""
    def __init__(self, family_login, login_account, client_id, *, clear_report_run=None):
        if (login_account not in FAMILY_NAMES
                or getattr(family_login,"user_id",None)!=login_account
                or getattr(family_login,"client_id",None)!=client_id):
            raise PermissionError("FAMILY_LOGIN_OWNER_MISMATCH")
        self.family_login=family_login
        self.account=login_account
        self.clear_report_run=clear_report_run

    def require_login(self):
        try:
            authenticated=self.family_login.require_login()
        except PermissionError:
            if self.clear_report_run is not None:
                self.clear_report_run()
            raise
        if authenticated!=self.account:
            raise PermissionError("FAMILY_ACCOUNT_MISMATCH")
        return authenticated

    def login(self, login_account, password):
        if login_account!=self.account:
            raise PermissionError("FAMILY_ACCOUNT_MISMATCH")
        if self.clear_report_run is not None:
            self.clear_report_run()
        return self.family_login.login(password)

    def logout(self):
        self.require_login()
        self.family_login.logout()
        if self.clear_report_run is not None:
            self.clear_report_run()
        return {"status":"LOGGED_OUT"}


class OnDemandReadCoordinator:
    """Read only the separately verified original Drive bytes for this user."""
    def __init__(self, auth, *, login_account, client_id, family_alias,
                 db_path, verified_drive_sha256, official_file_id):
        if (login_account not in FAMILY_NAMES
                or family_alias!=FAMILY_NAMES[login_account]
                or not isinstance(client_id,str)
                or not re.fullmatch(r"fam_[0-9a-f]{32}",client_id)
                or not isinstance(verified_drive_sha256,str)
                or not re.fullmatch(r"[0-9a-f]{64}",verified_drive_sha256)
                or not isinstance(official_file_id,str) or not official_file_id):
            raise ValueError("FAMILY_VERIFIED_DRIVE_BINDING_REQUIRED")
        self.auth=auth
        self.account=login_account
        self.client_id=client_id
        self.family_alias=family_alias
        self.file_id=official_file_id
        self.db_path=Path(db_path)
        self.source_sha256=verified_drive_sha256
        self.key=RESOURCE_KEYS[login_account]
        self.headers={self.key:{"resource_key":self.key}}

    def principal(self):
        self.auth.require_login()
        return SimpleNamespace(subject="account:"+self.account)

    def snapshot(self, key, principal):
        if (key!=self.key or getattr(principal,"subject",None)!="account:"+self.account
                or self.auth.require_login()!=self.account):
            raise PermissionError("FAMILY_WRONG_MEMBER_RESOURCE")
        io=_load(ROOT/"on_demand_drive_io.py","family_w8_on_demand_io")
        binding=io.Binding(self.account,self.client_id,self.file_id,self.family_alias)
        # No query about a member is permitted to fetch another member's DB.
        result=io.inspect(self.db_path,binding)
        if result["sha256"]!=self.source_sha256:
            raise RuntimeError("FAMILY_DRIVE_SOURCE_CHANGED")
        raw=self.db_path.read_bytes()
        if sha256(raw).hexdigest()!=self.source_sha256:
            raise RuntimeError("FAMILY_DRIVE_SOURCE_CHANGED_DURING_READ")
        return {"data":raw,"sha256":self.source_sha256,
                "source":"OFFICIAL_GOOGLE_DRIVE_DOWNLOADED_ON_DEMAND"}


def register_project_mandate(config, project_sources, family_alias):
    """Resolve the authenticated Project's persistent settings alongside its staged files."""
    source_path = Path(project_sources['local_path'])
    source_bytes = source_path.read_bytes()
    if sha256(source_bytes).hexdigest() != project_sources['sha256']:
        raise PermissionError('PROJECT_SOURCES_BYTES_CHANGED')
    prefix = 'MENU04_REGISTERED_MANDATE='
    rows = [line[len(prefix):] for line in source_bytes.decode('utf-8-sig').splitlines()
            if line.startswith(prefix)]
    if len(rows) != 1:
        raise ValueError('PROJECT_MANDATE_REGISTRATION_REQUIRED')
    registration = json.loads(rows[0])
    if registration['member'] != family_alias:
        raise PermissionError('PROJECT_MANDATE_REGISTRATION_MISMATCH')

    def registered_file(record):
        filename = record['file_name']
        if (not re.fullmatch(r'[A-Za-z0-9_-]+\.json', filename)
                or not re.fullmatch(r'[A-Za-z0-9_-]+', record['drive_file_id'])):
            raise PermissionError('PROJECT_MANDATE_REGISTRATION_MISMATCH')
        source = source_path.with_name(filename)
        raw = source.read_bytes()
        if sha256(raw).hexdigest() != record['sha256']:
            raise PermissionError('PROJECT_MANDATE_BYTES_CHANGED')
        return raw, {'local_path': str(source.resolve()), 'sha256': record['sha256'],
                     'drive_file_id': record['drive_file_id']}

    _, descriptor = registered_file(registration)
    if 'issuer_structure_source' in registration:
        raw, issuer_source = registered_file(registration['issuer_structure_source'])
        rows = json.loads(raw)['rows']
        structures = {}
        for symbol, row in rows.items():
            facts = row['official_evidence']
            if facts['symbol'] != symbol or facts['schema_version'] != 'Family.W8.IssuerFacts.v1':
                raise ValueError('PROJECT_ISSUER_STRUCTURE_IDENTITY_MISMATCH')
            # Only independent issuer observations may supplement missing ETF structure.
            # Ignore saved conclusions, valuations and client approval fields.
            keys = ('symbol', 'retrieved_at', 'as_of', 'source_url', 'fund_status',
                    'mandate', 'nav_redemption_status')
            structures[symbol] = {key: facts[key] for key in keys if key in facts}
            structures[symbol].update(source_sha256=issuer_source['sha256'],
                                      drive_file_id=issuer_source['drive_file_id'])
        config['registered_issuer_structures'] = structures
    owner = config.get('owner_etf_constraints_source')
    if owner is None:
        raise ValueError('PROJECT_OWNER_ETF_CONSTRAINTS_SOURCE_REQUIRED')
    config['owner_etf_constraints_source'] = {**owner, 'mandate_source': descriptor}


def build_project_menu(*, family_login, project_name, login_account,
                       client_id, family_alias, downloaded_db_path,
                       official_drive_file_id, verified_drive_sha256,
                       trusted_analysis_source_producer=None,
                       native_source_config=None,
                       member_v82_source_config=None, registered_project_sources=None,
                       official_holdings_decision=None,
                       official_holdings_previous_snapshot=None,
                       trusted_w6_current_input_producer=None,
                       approved_w6_archive=None, approved_w6_renderer=None,
                       report_store=None, other_handlers=None,
                       completion_checks=None, official_report_folder_id=None,
                       report_staging_dir=None, mutation_staging_dir=None,
                       trusted_report_archive_reader=None,
                       trusted_member_w6_receiver=None,
                       trusted_public_fetcher=None, trusted_account_change=None,
                       family03_market_reader=None):
    """Return the existing W7 menu without using a permanent Python host."""
    if trusted_member_w6_receiver is not None and (
            not callable(trusted_member_w6_receiver)
            or trusted_w6_current_input_producer is not None
            or member_v82_source_config is None or report_store is not None
            or official_report_folder_id is None):
        raise ValueError("W6_MEMBER_REPORT_RECEIVER_CONFIGURATION")
    if trusted_member_w6_receiver is not None and approved_w6_archive is not None and approved_w6_renderer is not None:
        raise ValueError("W6_RENDERER_SOURCE_CONFLICT")

    last_member_run = None

    def remember_member_run(request, result):
        nonlocal last_member_run
        last_member_run = None if request is None else (deepcopy(request), deepcopy(result))

    auth=FamilyLoginAdapter(family_login,login_account,client_id, clear_report_run=(
        lambda: remember_member_run(None, None)) if trusted_member_w6_receiver is not None else None)
    coordinator=OnDemandReadCoordinator(
        auth,login_account=login_account,client_id=client_id,
        family_alias=family_alias,db_path=downloaded_db_path,
        official_file_id=official_drive_file_id,
        verified_drive_sha256=verified_drive_sha256)
    official=_load(ROOT/"official_family_entry.py","family_w8_on_demand_entry")
    source_module=_load(ROOT/"on_demand_current_sources.py","family_w8_current_sources")
    if registered_project_sources is not None and member_v82_source_config is None:
        raise ValueError('PROJECT_MEMBER_V82_CONFIG_REQUIRED')
    if member_v82_source_config is not None:
        if trusted_analysis_source_producer is not None or native_source_config is not None:
            raise ValueError('CONFLICTING_NATIVE_SOURCE_PRODUCERS')
        config=dict(member_v82_source_config)
        if config.get('client_id')!=client_id or config.get('source_db_sha256')!=verified_drive_sha256:
            raise PermissionError('MEMBER_V82_CONFIG_CLIENT_OR_DB_MISMATCH')
        if config.get('member_db_path') is not None and Path(config['member_db_path']).resolve()!=Path(downloaded_db_path).resolve():
            raise PermissionError('MEMBER_V82_DB_OVERRIDE_REJECTED')
        config['member_db_path']=str(Path(downloaded_db_path).resolve())
        config['member_drive_binding']={'account':login_account,'client_id':client_id,
            'file_id':official_drive_file_id,'family_alias':family_alias}
        member=_load(ROOT/'member_v82_analysis.py','family_w8_member_v82_source')
        if registered_project_sources is None:
            trusted_analysis_source_producer=member.MemberV82SourceProducer(**config)
        else:
            def registered_producer(snapshot, payload):
                auth.require_login()
                current_config = dict(config)
                register_project_mandate(current_config, registered_project_sources, family_alias)
                return member.MemberV82SourceProducer(**current_config)(snapshot, payload)
            trusted_analysis_source_producer = registered_producer
    if native_source_config is not None:
        if trusted_analysis_source_producer is not None:
            raise ValueError('CONFLICTING_NATIVE_SOURCE_PRODUCERS')
        config=dict(native_source_config)
        if config.get('flow','HOLDINGS_ANALYSIS')!='HOLDINGS_ANALYSIS':
            raise ValueError('MENU04_INCOMPLETE_DEPLOYMENT_DIAGNOSTIC_NOT_A_PRODUCTION_ENTRY')
        if config.get('db_path') is not None and Path(config['db_path']).resolve()!=Path(downloaded_db_path).resolve():
            raise PermissionError('NATIVE_PRODUCER_DB_OVERRIDE_REJECTED')
        config['db_path']=downloaded_db_path
        native=_load(ROOT/'native_asset_source.py','family_w8_native_source')
        trusted_analysis_source_producer=native.AssetSourceProducer(**config)
    def current_source_provider(snapshot):
        try:
            return source_module.build_current_sources(snapshot,downloaded_db_path)
        except sqlite3.OperationalError:
            return {"status":"CURRENT_SOURCE_SCHEMA_UNAVAILABLE",
                    "client_id":snapshot["client_id"],
                    "source_db_sha256":snapshot["source_sha256"],
                    "missing":["official_target_funding_views_and_snapshot_schema"],
                    "trade_authorization":"NONE"}
    handlers=dict(other_handlers or {})
    # The on-demand runtime owns the public research/news tool handoff as
    # well as the authenticated current-holdings-only source for menu 09.
    public_module=_load(ROOT/"on_demand_public.py","family_w8_public_menu")
    public_entry=official.OfficialFamilyEntry(
        auth=auth,login_account=login_account,client_id=client_id,
        coordinator=coordinator,principal_provider=coordinator.principal)
    public=public_module.public_handlers(
        public_entry,auth,trusted_public_fetcher=trusted_public_fetcher,
        trusted_account_change=trusted_account_change)
    if set(public)&set(handlers):
        raise ValueError("CONFLICTING_FAMILY_PUBLIC_HANDLERS")
    handlers.update(public)
    if mutation_staging_dir is not None:
        mutations=_load(ROOT/"on_demand_mutations.py",
                        "family_w8_on_demand_mutations")
        stager=mutations.OnDemandMutationStager(
            auth=auth,login_account=login_account,client_id=client_id,
            family_alias=family_alias,official_drive_file_id=official_drive_file_id,
            downloaded_db_path=downloaded_db_path,
            verified_drive_sha256=verified_drive_sha256,
            staging_dir=mutation_staging_dir)
        writes=mutations.mutation_handlers(stager)
        if set(writes)&set(handlers):
            raise ValueError("CONFLICTING_FAMILY_MUTATION_HANDLERS")
        handlers.update(writes)
    if "adjust_target" not in (other_handlers or {}):
        target_writer = handlers.get("adjust_target")
        advisor = _load(ROOT/"family03_guide.py", "family03_guide")
        equity = _load(ROOT/"equity_sleeve.py", "family03_equity")
        planner = _load(ROOT/"family03_plans.py", "family03_plans")
        prices = _load(ROOT/"family03_prices.py", "family03_prices")
        cached = prices.reader(Path(downloaded_db_path).resolve().parent/prices.ARCHIVE)
        def plan_prices(symbols):
            result=cached(symbols)
            missing=tuple(s for s in symbols if s not in result)
            if missing and family03_market_reader:
                result.update(family03_market_reader(missing))
            return result
        positions = _load(ROOT.parent/"W5"/"official_holdings_source.py","family03_positions")
        guide_target = planner.menu_handler(public_entry, family_alias,
            Path(downloaded_db_path).resolve().parent, equity, advisor, positions.project_official_holdings, market_reader=plan_prices)
        def adjust_target(payload):
            if payload.get("action") == "confirm_account":
                if target_writer is None:
                    return {"status":"FAMILY03_SOURCE_REQUIRED","缺項":"本人帳本寫回暫存目錄"}
                preview = guide_target({"action":"account_preview"})
                if preview["status"] != "FAMILY03_ACCOUNT_PREVIEW":
                    return preview
                target = _load(ROOT/"family03_target.py", "family03_full_target")
                return target_writer(target.confirmed_request(preview, payload, client_id))
            if target_writer is not None and ("record" in payload or "owner_confirmed" in payload):
                return target_writer(payload)
            return guide_target(payload)
        handlers["adjust_target"] = adjust_target
    # The legacy W6 report store uses a direct REST transport. Under the
    # Owner-approved ChatGPT execution model, hand verified upload receipts
    # back to the tool executor instead of pretending Python uploaded files.
    if report_store is None and official_report_folder_id is not None:
        def previous_report_lookup(payload):
            if not isinstance(payload,dict) or set(payload)-{"date"}:
                raise ValueError("INVALID_REPORT_LOOKUP_OPTIONS")
            date=payload.get("date")
            if date is not None:
                from datetime import date as date_type
                if not isinstance(date,str) or date_type.fromisoformat(date).isoformat()!=date:
                    raise ValueError("INVALID_REPORT_LOOKUP_DATE")
            auth.require_login()
            lookup={"status":"DRIVE_LOOKUP_REQUIRED","folder_id":official_report_folder_id,
                    "member_alias":family_alias,"date":date,"trade_authorization":"NONE",
                    "folder_listing":"LIST_ALL_CHILDREN_AND_PAGES_IN_FIXED_FOLDER",
                    "file_selection":"LATEST_MEMBER_MANIFEST_FOR_DATE_OR_LATEST",
                    "readback_verifier":"on_demand_report_delivery.verify_report_lookup"}
            if trusted_report_archive_reader is None:
                return lookup
            # Only an operator-installed connector may supply private bytes.
            # User-supplied menu payloads can select a date, never a file ID.
            archive=trusted_report_archive_reader(dict(lookup))
            verifier=_load(ROOT/"on_demand_report_delivery.py","family_w8_report_lookup")
            return verifier.verify_report_lookup(archive["manifest_file_id"],archive["manifest_bytes"],
                account=login_account,client_id=client_id,folder_id=official_report_folder_id,
                file_metadata=archive["file_metadata"],readbacks=archive["readbacks"],date=date)
        handlers["previous_report"]=previous_report_lookup

        if ((trusted_w6_current_input_producer is not None or trusted_member_w6_receiver is not None)
                and (approved_w6_archive is not None
                     or approved_w6_renderer is not None)
                and report_staging_dir is not None):
            entry=official.OfficialFamilyEntry(
                auth=auth, login_account=login_account, client_id=client_id,
                coordinator=coordinator, principal_provider=coordinator.principal)
            source_module=_load(ROOT/"formal_report_source.py",
                                "family_w8_nohost_formal_source")
            report_module=_load(ROOT/"on_demand_w6.py",
                                "family_w8_nohost_current_report")
            delivery_module=_load(ROOT/"on_demand_report_delivery.py",
                                  "family_w8_nohost_report_delivery")
            receiver_archive = approved_w6_archive
            receiver_renderer = approved_w6_renderer

            def render_member_run(formal_source, payload):
                if last_member_run is None:
                    return None
                request, result = deepcopy(last_member_run)
                rendered = trusted_member_w6_receiver(
                    formal_source, payload, request=request, result=result,
                    approved_w6_archive=receiver_archive, approved_w6_renderer=receiver_renderer)
                if not isinstance(rendered, dict) or (
                        rendered.get('source_db_sha256') != formal_source['source_db_sha256']
                        or rendered.get('source_digest') != formal_source['digest']
                        or rendered.get('run_id') != request['run_id']
                        or rendered.get('data_as_of') != request['evaluation_at']):
                    raise PermissionError("W6_MEMBER_RECEIVER_OUTPUT_BINDING")
                return rendered

            renderer = render_member_run if trusted_member_w6_receiver is not None else report_module.OnDemandW6Renderer(
                trusted_w6_current_input_producer, approved_w6_renderer,
                approved_w6_archive=approved_w6_archive)

            def stage_latest_report(payload):
                snapshot=entry.current_snapshot()
                source=source_module.build_report_source(
                    snapshot,account=login_account,expected_client_id=client_id)
                if not isinstance(payload,dict) or set(payload)-{"date","language"}:
                    raise ValueError("W6_REPORT_OPTIONS_INVALID")
                try:
                    rendered=renderer(source,payload)
                except ValueError as exc:
                    gaps = {"W6_MEMBER_ITEM_REVIEW_ONLY": "W6_SOURCE_REVIEW_RECEIVER_FOR_SCOPED_MEMBER_RESULTS"}
                    if trusted_member_w6_receiver is not None:
                        gaps["W6_FINANCIAL_SOURCE_TIME"] = "W6_SOURCE_REVIEW_RECEIVER_FOR_PERIOD_LABEL_AND_PUBLICATION_TIME"
                    if str(exc) not in gaps:
                        raise
                    return {"status":"REPORT_SOURCE_INCOMPATIBLE","source_error":str(exc),
                            "required":gaps[str(exc)],"trade_authorization":"NONE"}
                if rendered is None and trusted_member_w6_receiver is not None:
                    return {"status":"REPORT_INPUTS_REQUIRED",
                            "missing":["same_session_verified_menu04_run"],
                            "trade_authorization":"NONE"}
                plan=delivery_module.prepare_report_delivery(
                    rendered,account=login_account,client_id=client_id,
                    folder_id=official_report_folder_id,
                    output_dir=report_staging_dir)
                # Google Drive import_document supports the exact generated
                # HTML bytes. Give ChatGPT concrete per-artifact tool arguments
                # in the same menu 13 response, without inventing upload URI.
                html_available={row["artifact"] for row in plan["uploads"]}
                plan["html_imports"]={
                    item:delivery_module.prepare_verified_html_import(plan,item)
                    for item in ("index.html","report.html")
                    if item in html_available}
                # PDF/ZIP + manifest remain independently pending; never
                # elevate these partial HTML transfer plans to report PASS.
                return plan
            handlers["generate_report"]=stage_latest_report
        elif member_v82_source_config is not None and family_alias=="Joseph":
            requirements={"trusted_w6_current_input_producer":trusted_w6_current_input_producer or trusted_member_w6_receiver,
                          "approved_w6_archive_or_renderer":approved_w6_archive or approved_w6_renderer,
                          "report_staging_dir":report_staging_dir}
            missing=[name for name,value in requirements.items() if value is None]
            def registered_missing_report(payload):
                auth.require_login()
                if not isinstance(payload,dict) or set(payload)-{"date","language"}:
                    raise ValueError("W6_REPORT_OPTIONS_INVALID")
                return {"status":"REPORT_INPUTS_REQUIRED","missing":list(missing),
                        "trade_authorization":"NONE"}
            handlers.setdefault("generate_report",registered_missing_report)
        # Menu handlers here stage reports only; the upstream no-host W6
        # injection must not also attempt the legacy synchronous Drive store.
        trusted_w6_current_input_producer=None
        approved_w6_archive=None
        approved_w6_renderer=None
    return official.build_official_family_menu(
        auth=auth,project_name=project_name,login_account=login_account,
        client_id=client_id,coordinator=coordinator,
        principal_provider=coordinator.principal,
        trusted_analysis_source_producer=trusted_analysis_source_producer,
        official_holdings_decision=official_holdings_decision,
        official_holdings_previous_snapshot=official_holdings_previous_snapshot,
        official_drive_file_id=official_drive_file_id,
        trusted_w6_current_input_producer=trusted_w6_current_input_producer,
        approved_w6_archive=approved_w6_archive,
        approved_w6_renderer=approved_w6_renderer,
        report_store=report_store,
        current_source_provider=current_source_provider,
        member_report_run_observer=remember_member_run if trusted_member_w6_receiver is not None else None,
        other_handlers=handlers,
        completion_checks=completion_checks)

