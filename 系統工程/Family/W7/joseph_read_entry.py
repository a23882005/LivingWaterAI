"""Conversation-local menu 02 entry; loads the accepted W5 reader on demand.

Call with an existing JosephLogin instance after login. This entry does not
download files, grant writer permissions, project positions, or run engines.
"""
import importlib.util
from pathlib import Path


def read_my_data(auth, database):
    # Authenticate before importing business code or opening a private DB.
    auth.require_login()
    path = Path(__file__).resolve().parents[1] / 'W5' / 'family_input.py'
    spec = importlib.util.spec_from_file_location('family_w5_read_snapshot', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return auth.read_progress(database, module.read_snapshot)
