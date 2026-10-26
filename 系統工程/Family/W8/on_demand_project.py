"""Family W8 one-shot ChatGPT Project runtime; GitHub program + Drive SQLite.

The ChatGPT executor must obtain the exact user's official Drive DB first.
This adapter provides W7's 14-option menu with a local, read-only equivalent
of the B06 snapshot interface. It never deploys Python to a website, handles
no API credentials and never persists anything by itself. For menu writes,
reuse the separately approved on_demand_drive_io staged/backup/readback flow.
"""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import re


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
    def __init__(self, family_login, login_account, client_id):
        if (login_account not in FAMILY_NAMES
                or getattr(family_login,"user_id",None)!=login_account
                or getattr(family_login,"client_id",None)!=client_id):
            raise PermissionError("FAMILY_LOGIN_OWNER_MISMATCH")
        self.family_login=family_login
        self.account=login_account

    def require_login(self):
        authenticated=self.family_login.require_login()
        if authenticated!=self.account:
            raise PermissionError("FAMILY_ACCOUNT_MISMATCH")
        return authenticated

    def login(self, login_account, password):
        if login_account!=self.account:
            raise PermissionError("FAMILY_ACCOUNT_MISMATCH")
        return self.family_login.login(password)

    def logout(self):
        self.require_login()
        self.family_login.logout()
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


def build_project_menu(*, family_login, project_name, login_account,
                       client_id, family_alias, downloaded_db_path,
                       official_drive_file_id, verified_drive_sha256,
                       trusted_analysis_source_producer=None,
                       trusted_w6_current_input_producer=None,
                       approved_w6_archive=None, approved_w6_renderer=None,
                       report_store=None, other_handlers=None,
                       completion_checks=None, official_report_folder_id=None,
                       report_staging_dir=None, mutation_staging_dir=None,
                       trusted_public_fetcher=None, trusted_account_change=None):
    """Return the existing W7 menu without using a permanent Python host."""
    auth=FamilyLoginAdapter(family_login,login_account,client_id)
    coordinator=OnDemandReadCoordinator(
        auth,login_account=login_account,client_id=client_id,
        family_alias=family_alias,db_path=downloaded_db_path,
        official_file_id=official_drive_file_id,
        verified_drive_sha256=verified_drive_sha256)
    official=_load(ROOT/"official_family_entry.py","family_w8_on_demand_entry")
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
            return {"status":"DRIVE_LOOKUP_REQUIRED",
                    "folder_id":official_report_folder_id,
                    "member_alias":family_alias,
                    "date":date,"trade_authorization":"NONE"}
        handlers["previous_report"]=previous_report_lookup

        if (trusted_w6_current_input_producer is not None
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
            renderer=report_module.OnDemandW6Renderer(
                trusted_w6_current_input_producer, approved_w6_renderer,
                approved_w6_archive=approved_w6_archive)

            def stage_latest_report(payload):
                snapshot=entry.current_snapshot()
                source=source_module.build_report_source(
                    snapshot,account=login_account,expected_client_id=client_id)
                rendered=renderer(source,payload)
                return delivery_module.prepare_report_delivery(
                    rendered,account=login_account,client_id=client_id,
                    folder_id=official_report_folder_id,
                    output_dir=report_staging_dir)
            handlers["generate_report"]=stage_latest_report
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
        trusted_w6_current_input_producer=trusted_w6_current_input_producer,
        approved_w6_archive=approved_w6_archive,
        approved_w6_renderer=approved_w6_renderer,
        report_store=report_store,
        other_handlers=handlers,
        completion_checks=completion_checks)
