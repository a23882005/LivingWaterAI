"""Load authorized native modules; resolve only identical packaged schema names."""
import importlib.util
from pathlib import Path
import json
import hashlib
from jsonschema import Draft202012Validator

C_PATH = Path('系統工程/C-配置決策引擎＋Mentor整合/正式Runtime/C8C9_RUNTIME')
C_MODULES = {
    3:'C8C9_Work3_Context_Handoff_Adapter.py',
    4:'C8C9_Work4_V82_Integration_Adapter.py',
    5:'C8C9_Work5_V75_Integration_Adapter.py',
    6:'C8C9_Work6_Funding_Account_Isolation_Guard.py',
    7:'C8C9_Work7_SGOV_Runtime_Role_Integration.py',
    8:'C8C9_Work8_Protected_Holding_Client_Action_Protection.py',
    9:'C8C9_Work9_Unified_Deployment_Mentor_Return.py',
}


def load_c_module(repo_path, work):
    path = Path(repo_path).resolve() / C_PATH / C_MODULES[work]
    spec = importlib.util.spec_from_file_location('family_c8c9_' + str(work), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schema_root = Path(__file__).resolve().parent / 'schemas'
    lock = json.loads((schema_root.parent / 'frozen_schema_lock.json').read_text())
    recovered = {}
    for entry in lock['files']:
        candidate = schema_root.parent / entry['destination']
        if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('FROZEN_SCHEMA_INTEGRITY:' + candidate.name)
        recovered[candidate.name] = candidate
    # Keep core files untouched. Only redirect a missing schema path when the
    # same filename is physically packaged beside the approved module.
    for key, value in tuple(vars(module).items()):
        if key.endswith('_SCHEMA') and isinstance(value, Path) and not value.exists():
            candidate = path.parent / value.name
            if not candidate.is_file():
                candidate = recovered.get(value.name, candidate)
            if candidate.is_file():
                setattr(module, key, candidate)
        elif work == 5 and key.endswith('_SCHEMA_FILENAME') and value in recovered:
            # Work5 joins Path(__file__).parent / filename; an absolute locked
            # schema path preserves its original validator and cache.
            setattr(module, key, str(recovered[value]))
    return module


def check_c_dependencies(repo_path):
    rows = []
    for work in C_MODULES:
        module = load_c_module(repo_path, work)
        for name, value in vars(module).items():
            if name.endswith('_SCHEMA') and isinstance(value, Path):
                path = value
            elif name.endswith('_SCHEMA_FILENAME') and isinstance(value, str):
                path = Path(module.__file__).parent / value
            else:
                continue
            status = 'DEPENDENCY_MISSING'
            if path.is_file():
                Draft202012Validator.check_schema(json.loads(path.read_text()))
                status = 'SCHEMA_VALID'
            rows.append({'work':work,'constant':name,'filename':path.name,'status':status})
    return rows
