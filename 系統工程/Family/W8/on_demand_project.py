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
                       completion_checks=None):
    """Return the existing W7 menu without using a permanent Python host."""
    auth=FamilyLoginAdapter(family_login,login_account,client_id)
    coordinator=OnDemandReadCoordinator(
        auth,login_account=login_account,client_id=client_id,
        family_alias=family_alias,db_path=downloaded_db_path,
        official_file_id=official_drive_file_id,
        verified_drive_sha256=verified_drive_sha256)
    official=_load(ROOT/"official_family_entry.py","family_w8_on_demand_entry")
    return official.build_official_family_menu(
        auth=auth,project_name=project_name,login_account=login_account,
        client_id=client_id,coordinator=coordinator,
        principal_provider=coordinator.principal,
        trusted_analysis_source_producer=trusted_analysis_source_producer,
        trusted_w6_current_input_producer=trusted_w6_current_input_producer,
        approved_w6_archive=approved_w6_archive,
        approved_w6_renderer=approved_w6_renderer,
        report_store=report_store,
        other_handlers=other_handlers,
        completion_checks=completion_checks)
