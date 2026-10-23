"""Executable HTTP boundary checks; CI must provide PHP."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest

W7 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publish_discovery', W7/'deployment/publish_discovery.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

@pytest.mark.parametrize('method,path,extra,status', [
    ('GET','/family-connect/oauth/.well-known/oauth-authorization-server',{},200),
    ('GET','/family-connect/mcp/.well-known/oauth-protected-resource',{},200),
    ('GET','/family-connect/mcp',{},401),
    ('POST','/family-connect/mcp',{'HTTP_AUTHORIZATION':'Bearer fake'},401),
    ('GET','/family-connect/oauth/authorize',{},503),
    ('POST','/family-connect/oauth/token',{},503),
    ('GET','/family-connect/unknown',{},404),
    ('GET','/family-connect/mcp?x=1',{},400),
    ('GET','/family-connect/%2e%2e',{},400),
    ('GET','/family-connect/mcp',{'HTTP_HOST':'evil.invalid'},403),
    ('GET','/family-connect/mcp',{'HTTP_ORIGIN':'https://evil.invalid'},403),
    ('GET','/family-connect/mcp',{'HTTPS':''},400),
    ('DELETE','/family-connect/mcp',{},404),
])
def test_http_boundary(method,path,extra,status):
    if not shutil.which('php'): pytest.skip('PHP required in CI')
    server={'HTTPS':'on','HTTP_HOST':'www.happihelp.com','REQUEST_METHOD':method,'REQUEST_URI':path,**extra}
    script="$_SERVER=json_decode(getenv('FAMILY_TEST_SERVER'),true);register_shutdown_function(function(){fwrite(STDERR,(string)http_response_code());});require getenv('FAMILY_TEST_GATEWAY');"
    env={**os.environ,'FAMILY_TEST_SERVER':json.dumps(server),'FAMILY_TEST_GATEWAY':str(W7/'public_discovery/index.php')}
    out=subprocess.run(['php','-r',script],env=env,capture_output=True,text=True,check=True)
    assert out.stderr==str(status)
    data=json.loads(out.stdout)
    if status==200 and 'issuer' in data:
        assert data['issuer']=='https://www.happihelp.com/family-connect/oauth'
        assert data['token_endpoint_auth_methods_supported']==['none']
        assert data['code_challenge_methods_supported']==['S256']
    elif status==200:
        assert data['resource']=='https://www.happihelp.com/family-connect/mcp'
    else: assert 'error' in data

def test_install_backup_and_refuse_unknown(tmp_path, monkeypatch):
    stage=tmp_path/'stage';stage.mkdir()
    for n in publisher.NAMES:shutil.copyfile(W7/'public_discovery'/n,stage/n)
    (stage/'manifest.json').write_text(json.dumps({'schema':publisher.SCHEMA,'files':publisher.validate(stage)}))
    monkeypatch.setattr(publisher,'__file__',str(stage/'publish_discovery.py'))
    root=tmp_path/'public_html';root.mkdir();(root/'index.html').write_text('existing site')
    publisher.install(root)
    assert (root/'family-connect').stat().st_mode & 0o777 == 0o755
    publisher.install(root)
    assert list((tmp_path/'.family-discovery-backups').glob('snapshot-*'))
    assert (root/'index.html').read_text()=='existing site'
    (root/'family-connect'/'unexpected.txt').write_text('preserve')
    with pytest.raises(AssertionError):publisher.install(root)
    assert (root/'family-connect'/'unexpected.txt').read_text()=='preserve'

def test_symlink_refused(tmp_path,monkeypatch):
    root=tmp_path/'public_html';root.mkdir()
    (root/'family-connect').symlink_to(tmp_path,target_is_directory=True)
    stage=tmp_path/'stage';stage.mkdir()
    for n in publisher.NAMES:shutil.copyfile(W7/'public_discovery'/n,stage/n)
    (stage/'manifest.json').write_text(json.dumps({'schema':publisher.SCHEMA,'files':publisher.validate(stage)}))
    monkeypatch.setattr(publisher,'__file__',str(stage/'publish_discovery.py'))
    with pytest.raises(AssertionError):publisher.install(root)
