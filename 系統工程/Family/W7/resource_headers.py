"""B05 external metadata/ACL format. B06 owns locking; B07 supplies identity.

This module never accepts account names from an HTTP/tool payload. Callers pass
a principal obtained from the server's verified session. Metadata is not a lock.
"""
import json
import re
from dataclasses import dataclass

SCHEMA = 'Family-resource-header-v1'
FIELDS = {'schema','resource_key','binding','file_id','policy_ref','state','readers','updater'}
SUBJECT = re.compile(r'(?:account:[A-Za-z0-9_.\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U0002fa1f-]{1,80}|service:[A-Za-z0-9_.-]{1,80})\Z')

def _unique(pairs):
    result = {}
    for key,value in pairs:
        if key in result: raise ValueError('DUPLICATE_KEY')
        result[key] = value
    return result

def _subjects(values):
    if not isinstance(values,list) or any(not isinstance(x,str) or not SUBJECT.fullmatch(x) for x in values):
        raise ValueError('INVALID_SUBJECTS')
    if len(set(values)) != len(values): raise ValueError('DUPLICATE_SUBJECT')

def validate_header(h):
    if not isinstance(h,dict) or set(h) != FIELDS or h['schema'] != SCHEMA:
        raise ValueError('INVALID_HEADER_SCHEMA')
    if not isinstance(h['resource_key'],str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,100}',h['resource_key']):
        raise ValueError('INVALID_RESOURCE_KEY')
    if not isinstance(h['policy_ref'],str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,100}',h['policy_ref']):
        raise ValueError('INVALID_POLICY_REF')
    if h['binding'] not in ('BOUND','PENDING_B07'): raise ValueError('INVALID_BINDING')
    if h['binding']=='BOUND':
        if not isinstance(h['file_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,200}',h['file_id']):
            raise ValueError('INVALID_FILE_ID')
    elif h['file_id'] is not None: raise ValueError('PENDING_HAS_ID')
    _subjects(h['readers'])
    if h['updater'] is not None: _subjects([h['updater']])
    if h['state']=='Close':
        if h['readers'] or h['updater'] is not None: raise ValueError('CLOSE_HAS_HOLDER')
    elif h['state']=='Read':
        if not h['readers'] or h['updater'] is not None: raise ValueError('INVALID_READ_STATE')
    elif h['state']=='Update':
        if h['readers'] or h['updater'] is None: raise ValueError('INVALID_UPDATE_STATE')
    else: raise ValueError('INVALID_STATE')
    if h['binding']!='BOUND' and h['state']!='Close': raise ValueError('UNBOUND_ACTIVE')
    return h

def parse_header(markdown):
    blocks=re.findall(r'^```json\s*\n(.*?)\n```\s*$',markdown,re.M|re.S)
    if len(blocks)!=1: raise ValueError('ONE_HEADER_REQUIRED')
    return validate_header(json.loads(blocks[0],object_pairs_hook=_unique))

def render_header(header):
    validate_header(header)
    return '# 資源管理表頭\n\n```json\n'+json.dumps(header,ensure_ascii=False,indent=2)+'\n```\n\n狀態由B06共同writer維護；此表頭本身不提供互斥鎖。\n'

def validate_policies(policies):
    if not isinstance(policies,dict): raise ValueError('INVALID_POLICIES')
    for key,p in policies.items():
        if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,100}',key):
            raise ValueError('INVALID_POLICY_KEY')
        if not isinstance(p,dict) or set(p)!={'read','update'}: raise ValueError('INVALID_POLICY')
        _subjects(p['read']);_subjects(p['update'])
    return policies

@dataclass(frozen=True)
class VerifiedPrincipal:
    subject: str
    expires_at: int

def authorize(header,policies,principal,operation,now):
    validate_header(header);validate_policies(policies)
    if not isinstance(principal,VerifiedPrincipal): raise PermissionError('VERIFIED_PRINCIPAL_REQUIRED')
    if not isinstance(principal.subject,str) or not SUBJECT.fullmatch(principal.subject):
        raise PermissionError('INVALID_PRINCIPAL')
    if type(principal.expires_at) is not int or type(now) is not int or now >= principal.expires_at:
        raise PermissionError('SESSION_EXPIRED')
    if operation not in ('read','update'): raise PermissionError('UNKNOWN_OPERATION')
    if header['binding']!='BOUND': raise PermissionError('RESOURCE_UNBOUND')
    policy=policies.get(header['policy_ref'])
    if policy is None or principal.subject not in policy[operation]: raise PermissionError('ACCESS_DENIED')
    return header['file_id']

def load_catalog(headers,policies):
    validate_policies(policies)
    catalog={};ids=set()
    for text in headers:
        h=parse_header(text)
        if h['resource_key'] in catalog: raise ValueError('DUPLICATE_RESOURCE')
        if h['policy_ref'] not in policies: raise ValueError('MISSING_POLICY')
        if h['file_id'] is not None:
            if h['file_id'] in ids: raise ValueError('DUPLICATE_FILE_ID')
            ids.add(h['file_id'])
        catalog[h['resource_key']]=h
    return catalog
