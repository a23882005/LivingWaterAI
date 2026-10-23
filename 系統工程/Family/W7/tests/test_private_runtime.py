import json
import os
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from private_runtime import provision,read_private
from private_service_config import load_key


def config(tmp_path):
    p=tmp_path/'input.json'
    p.write_text(json.dumps({'schema':'Family-B07-private-runtime-v1','enabled':False,
        'source_commit':'a'*40,'backup_access_verified':'OWNER_ONLY',
        'resource_config':{'schema':'Family-B06-private-resource-config-v1','resources':{str(i):{} for i in range(6)},'backup_folder':'private','pending':[]},
        'google_oauth':{'client_id':'synthetic','client_secret':'synthetic','refresh_token':'synthetic'}}))
    p.chmod(0o600);return p


def test_repeat_preserves_key_and_backups(tmp_path):
    p=config(tmp_path);root=tmp_path/'private';assert provision(root,p)['stable_key']
    key=load_key(root);old=read_private(root/'runtime.json')
    c=json.loads(p.read_text());c['source_commit']='b'*40;p.write_text(json.dumps(c))
    assert provision(root,p)['status']=='PASS';assert load_key(root)==key
    assert [read_private(x) for x in (root/'backups').iterdir()]==[old]


def test_missing_key_never_regenerated(tmp_path):
    p=config(tmp_path);root=tmp_path/'private';provision(root,p);(root/'server.key').unlink()
    with pytest.raises(FileNotFoundError):provision(root,p)
    assert not (root/'server.key').exists()


def test_public_input_rejected(tmp_path):
    p=config(tmp_path);p.chmod(0o644)
    with pytest.raises(ValueError):provision(tmp_path/'private',p)


def test_corrupt_key_preserved(tmp_path):
    p=config(tmp_path);root=tmp_path/'private';provision(root,p);(root/'server.key').write_bytes(b'bad')
    with pytest.raises(ValueError):provision(root,p)
    assert (root/'server.key').read_bytes()==b'bad'


def test_enabled_config_rejected(tmp_path):
    p=config(tmp_path);c=json.loads(p.read_text());c['enabled']=True;p.write_text(json.dumps(c))
    with pytest.raises(ValueError):provision(tmp_path/'private',p)
    assert not (tmp_path/'private').exists()


def test_symlink_config_rejected(tmp_path):
    p=config(tmp_path);link=tmp_path/'link';link.symlink_to(p)
    with pytest.raises(OSError):provision(tmp_path/'private',link)
