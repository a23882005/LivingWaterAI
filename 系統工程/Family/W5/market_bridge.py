"""Read the approved W3 entrypoint without modifying its feed."""
import hashlib,json
from datetime import datetime,timezone
import importlib.util
from pathlib import Path
from family_input import digest, InputError


def resolve_macro_feed(repo_path,source=None):
    if source is None:return Path(repo_path).resolve()/'系統工程/總經V70/V70_macro_latest.json'
    if source.get('schema_version')!='Family.W5.VerifiedMacroFeedSource.v1':
        raise InputError('MACRO_FEED_SOURCE_SCHEMA')
    path=Path(source['local_path']).resolve(strict=True)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:
        raise InputError('MACRO_FEED_SOURCE_CHANGED')
    return path


def read_macro_snapshot(repo_path, *, source_commit, capture_bound=False,source=None):
    root = Path(repo_path).resolve()
    reader = root / '系統工程/總經V70/P70-5.py'
    feed = resolve_macro_feed(root,source)
    reader_before = reader.read_bytes()
    feed_before = feed.read_bytes()
    spec = importlib.util.spec_from_file_location('family_w5_macro_reader', reader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if source is not None:
        # Select a verified input file; the original W3 reader and validation
        # algorithm remain unchanged. No default production feed is replaced.
        module.SOURCE=feed
    raw = module.read_macro(root)
    if reader.read_bytes() != reader_before or feed.read_bytes() != feed_before:
        raise InputError('MACRO_SOURCE_CHANGED_DURING_READ')
    if raw!=json.loads(feed_before.decode('utf-8-sig')):
        raise InputError('MACRO_READER_SELECTED_SOURCE_MISMATCH')
    capture={'schema_version':'Family.W5.SourceCaptureBound.v1',
        'captured_at':datetime.now(timezone.utc).isoformat(),
        'source_sha256':hashlib.sha256(feed_before).hexdigest(),'payload_digest':digest(raw),
        **({'source_selection_digest':digest(source)} if source is not None else {}),
        'basis':'EXACT_SOURCE_BYTES_READ_AND_HASH_CHECKED',
        'scope':'KNOWN_BY_BOUND_FOR_CURRENT_ANALYSIS__NOT_PUBLICATION_TIME_OR_HISTORICAL_PIT'}
    return {'payload': raw, 'digest': digest(raw), 'asOf': raw['asOf'],
            **({'capture_receipt':capture} if capture_bound else {}),
            'source_commit': source_commit, 'source_path': str(feed.relative_to(root)) if feed.is_relative_to(root) else str(feed),
            'source_sha256': hashlib.sha256(feed_before).hexdigest(),
            'reader_sha256': hashlib.sha256(reader_before).hexdigest(),
            'data_provenance': 'SOURCE_BACKED'}
