import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_runtime import provision
from private_account_service import account_binding, load_manager, load_router


def resource():
    header = dict(schema='Family-resource-header-v1', resource_key='accounts',
                  binding='BOUND', file_id='account-db', policy_ref='accounts',
                  state='Close', readers=[], updater=None)
    mapping = dict(parent_id='private', journal_id='journal',
                   journal_parent_id='private', header_id='header', header_template=header)
    return dict(schema='Family-B06-private-resource-config-v1',
                resources={'account-db': mapping, **{str(i): {} for i in range(5)}},
                headers={'accounts': header}, backup_folder='backup', pending=[],
                deployment=dict(single_writer_host=True, lock_dir='resource-locks'))


def runtime(tmp_path):
    data = dict(schema='Family-B07-private-runtime-v1', enabled=False,
                source_commit='a'*40, backup_access_verified='OWNER_ONLY',
                resource_config=resource(), google_oauth=dict(client_id='test',
                client_secret='test', refresh_token='test'))
    source=tmp_path/'input.json'; source.write_text(json.dumps(data)); source.chmod(0o600)
    root=tmp_path/'service'; provision(root, source)
    return root


class NoNetwork:
    def __init__(self, **kwargs): pass
    def call(self, *args, **kwargs): raise AssertionError('Unexpected Drive call')


def test_constructs_without_network_and_uses_stable_identity(tmp_path):
    root=runtime(tmp_path)
    before={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    first=load_manager(root, transport_factory=NoNetwork)
    second=load_manager(root, transport_factory=NoNetwork)
    assert first._mac('test','value') == second._mac('test','value')
    assert before == {p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    headers, policies, backend, locks = first.store.args
    assert set(headers) == set(policies) == {'accounts'}
    assert set(backend.resources) == {'account-db'}
    assert locks == root/'resource-locks'


@pytest.mark.parametrize('field,value', [('file_id','other'),('policy_ref','private.mou'),
                                       ('resource_key','family.mou'),('binding','PENDING')])
def test_rejects_mismatched_account_mapping(field,value):
    r=resource(); r['headers']['accounts']=copy.deepcopy(r['headers']['accounts'])
    r['headers']['accounts'][field]=value
    with pytest.raises((ValueError,KeyError)): account_binding(r)


@pytest.mark.parametrize('field,value', [('lock_dir','../public_html'),('single_writer_host',False)])
def test_rejects_unsafe_deployment(field,value):
    r=resource();r['deployment'][field]=value
    with pytest.raises(ValueError):account_binding(r)


def test_missing_key_does_not_mint_identity(tmp_path):
    root=runtime(tmp_path);(root/'server.key').unlink()
    with pytest.raises(FileNotFoundError):load_manager(root,transport_factory=NoNetwork)
    assert not (root/'server.key').exists()


def test_symlink_lock_directory_rejected(tmp_path):
    root=runtime(tmp_path);(root/'resource-locks').rmdir()
    (root/'resource-locks').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):load_manager(root,transport_factory=NoNetwork)


def entry(root, **overrides):
    value=dict(schema='Family-B07-private-entry-v1', base='/family-account',
               connection_scope='family-b07-stable', origin='https://example.test',
               oauth_clients={'verified-client':['https://client.test/callback']})
    value.update(overrides)
    p=root/'entry.json';p.write_text(json.dumps(value));p.chmod(0o600)


def test_real_router_metadata_and_host_boundary_without_drive(tmp_path):
    root=runtime(tmp_path);entry(root)
    router=load_router(root,transport_factory=NoNetwork)
    url='/.well-known/oauth-authorization-server/family-account/oauth'
    status,headers,body=router.handle('GET',url,{'Host':'example.test'})
    assert status==200
    assert json.loads(body)['issuer']=='https://example.test/family-account/oauth'
    assert router.handle('GET',url,{'Host':'attacker.test'})[0]==403
    assert router.handle('GET','/unrelated',{'Host':'example.test'})[0]==404
    assert (root/'rate.db').stat().st_mode & 0o777 == 0o600
    # A second process can reload the same private limiter after a request.
    load_router(root,transport_factory=NoNetwork)


@pytest.mark.parametrize('override', [dict(base='/../x'),dict(connection_scope=''),
    dict(origin='http://example.test'),dict(oauth_clients={})])
def test_router_rejects_unverified_configuration(tmp_path,override):
    root=runtime(tmp_path);entry(root,**override)
    with pytest.raises(ValueError):load_router(root,transport_factory=NoNetwork)


def test_router_rejects_symlink_rate_database(tmp_path):
    root=runtime(tmp_path);entry(root)
    target=tmp_path/'outside';target.write_bytes(b'unchanged')
    (root/'rate.db').symlink_to(target)
    with pytest.raises(OSError):load_router(root,transport_factory=NoNetwork)
    assert target.read_bytes()==b'unchanged'
