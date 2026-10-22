"""Read-only repository resource catalog. Trusted configuration, never user input.

Database admission stays in resource_headers; B06 owns mutable Drive I/O.
Repository resources are pinned by Git blob hash; no source write operation.
"""
import hashlib
import re
from pathlib import PurePosixPath
from resource_headers import VerifiedPrincipal, validate_policies, SUBJECT

CATEGORIES = {'readonly_resource', 'qa_only', 'source_only'}

def validate_source_catalog(catalog, inventory, policies):
    validate_policies(policies)
    expected = {r['path'] for r in inventory['rows']}
    if len(expected) != len(inventory['rows']):
        raise ValueError('DUPLICATE_INVENTORY')
    entries = catalog['entries']
    if {r['path'] for r in entries} != expected or len(entries) != len(expected):
        raise ValueError('INCOMPLETE_COVERAGE')
    for row in entries:
        path = PurePosixPath(row['path'])
        if path.is_absolute() or '..' in path.parts or str(path) != row['path']:
            raise ValueError('INVALID_PATH')
        if row['category'] not in CATEGORIES or not re.fullmatch('[0-9a-f]{40}', row['git_blob']):
            raise ValueError('INVALID_SOURCE')
        policy = policies.get(row['policy_ref'])
        if policy is None or policy['update']:
            raise ValueError('SOURCE_MUST_BE_READONLY')
        if row['state'] != 'Close' or row['readers'] or row['updater'] is not None:
            raise ValueError('STATIC_SOURCE_HAS_HOLDER')
        if row['category'] == 'readonly_resource':
            if PurePosixPath(row['header_path']).parent != path.parent:
                raise ValueError('HEADER_NOT_COLOCATED')
        elif row['header_path'] is not None:
            raise ValueError('NONRESOURCE_HEADER')
    return {r['path']: r for r in entries}

def verified_source_bytes(row, policies, principal, operation, now, content):
    """Return bytes only for approved runtime resources and verified principals.

Caller supplies the trusted catalog row, not a caller-supplied path/hash/ACL.
QA and source-governance entries cannot be opened by the runtime reader.
"""
    validate_policies(policies)
    if operation != 'read' or row['category'] != 'readonly_resource':
        raise PermissionError('NOT_RUNTIME_READ')
    if (not isinstance(principal, VerifiedPrincipal)
        or not isinstance(principal.subject, str)
        or not SUBJECT.fullmatch(principal.subject)
        or type(principal.expires_at) is not int or type(now) is not int
        or now >= principal.expires_at):
        raise PermissionError('VERIFIED_SESSION_REQUIRED')
    policy = policies.get(row['policy_ref'])
    if policy is None or policy['update'] or principal.subject not in policy['read']:
        raise PermissionError('ACCESS_DENIED')
    digest = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
    if digest != row['git_blob']:
        raise ValueError('SOURCE_HASH_MISMATCH')
    return content
