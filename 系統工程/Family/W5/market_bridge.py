"""Read the approved W3 entrypoint without modifying its feed."""
import hashlib
import importlib.util
from pathlib import Path
from family_input import digest


def read_macro_snapshot(repo_path, *, source_commit):
    root = Path(repo_path).resolve()
    reader = root / '系統工程/總經V70/P70-5.py'
    feed = root / '系統工程/總經V70/V70_macro_latest.json'
    spec = importlib.util.spec_from_file_location('family_w5_macro_reader', reader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = module.read_macro(root)
    return {'payload': raw, 'digest': digest(raw), 'asOf': raw['asOf'],
            'source_commit': source_commit, 'source_path': str(feed.relative_to(root)),
            'source_sha256': hashlib.sha256(feed.read_bytes()).hexdigest(),
            'reader_sha256': hashlib.sha256(reader.read_bytes()).hexdigest(),
            'data_provenance': 'SOURCE_BACKED'}
