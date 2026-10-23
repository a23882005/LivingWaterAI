"""Publish isolated discovery only; authentication remains unavailable."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request

NAMES = ('index.php', '.htaccess')
SCHEMA = 'family-discovery-v1'


def validate(folder):
    for name in NAMES:
        path = folder / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('INVALID_DISCOVERY_FILE')
    return {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in NAMES}


def build():
    source = Path(__file__).resolve().parents[1] / 'public_discovery'
    manifest = {'schema': SCHEMA, 'files': validate(source)}
    stage = Path('build/family-discovery/private')
    stage.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        shutil.copyfile(source / name, stage / name)
    (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copyfile(__file__, stage / 'publish_discovery.py')
    print(json.dumps(manifest))


def install(root):
    root = Path(root).absolute()
    assert root.name == 'public_html' and root.is_dir() and not root.is_symlink()
    source = Path(__file__).resolve().parent
    manifest = json.loads((source / 'manifest.json').read_text())
    assert manifest == {'schema': SCHEMA, 'files': validate(source)}
    target = root / 'family-connect'
    assert not target.is_symlink()
    backup = None
    if target.exists():
        assert target.is_dir()
        assert {p.name for p in target.iterdir()} == set(NAMES) | {'manifest.json'}
        assert not any(p.is_symlink() for p in target.iterdir())
        old = json.loads((target / 'manifest.json').read_text())
        assert old == {'schema': SCHEMA, 'files': validate(target)}, 'Unmanaged or changed target'
        backups = root.parent / '.family-discovery-backups'
        assert not backups.is_symlink()
        backups.mkdir(mode=0o700, exist_ok=True)
        os.chmod(backups, 0o700)
        backup = Path(tempfile.mkdtemp(prefix='snapshot-', dir=backups)) / 'family-connect'
        shutil.copytree(target, backup)
        for item in backup.rglob('*'):
            os.chmod(item, 0o700 if item.is_dir() else 0o600)
        os.chmod(backup, 0o700)
    staging = Path(tempfile.mkdtemp(prefix='.discovery-', dir=root.parent))
    try:
        for name in NAMES + ('manifest.json',):
            shutil.copyfile(source / name, staging / name)
            os.chmod(staging / name, 0o644)
        os.chmod(staging, 0o755)
        target.mkdir(mode=0o755, exist_ok=True)
        os.chmod(target, 0o755)
        try:
            for name in NAMES + ('manifest.json',):
                os.replace(staging / name, target / name)
            assert validate(target) == manifest['files']
        except BaseException:
            if backup:
                for name in NAMES + ('manifest.json',):
                    shutil.copyfile(backup / name, target / name)
                    os.chmod(target / name, 0o644)
            else:
                shutil.rmtree(target)
            raise
    finally:
        shutil.rmtree(staging)
    print('DISCOVERY_INSTALL_PASS')


def verify(base):
    from urllib.error import HTTPError
    prefix = base.rstrip('/') + '/family-connect'
    cases = [('/oauth/.well-known/oauth-authorization-server', 200),
             ('/mcp/.well-known/oauth-protected-resource', 200),
             ('/mcp', 401), ('/oauth/token', 503), ('/unknown', 404)]
    for path, status in cases:
        req = urllib.request.Request(prefix + path, headers={'Cache-Control': 'no-cache'})
        try: response = urllib.request.urlopen(req, timeout=30)
        except HTTPError as exc: response = exc
        with response:
            assert response.status == status, (path, response.status)
            data = json.loads(response.read())
            assert 'no-store' in response.headers.get('Cache-Control', '')
            if path.endswith('oauth-authorization-server'):
                assert data['issuer'] == prefix + '/oauth'
                assert data['code_challenge_methods_supported'] == ['S256']
            if path.endswith('oauth-protected-resource'):
                assert data['resource'] == prefix + '/mcp'
            if path == '/mcp':
                assert response.headers['WWW-Authenticate'] == 'Bearer resource_metadata="' + prefix + '/mcp/.well-known/oauth-protected-resource"'
        print('DISCOVERY_HTTPS_PASS', path, status)


if __name__ == '__main__':
    {'build': build, 'install': lambda: install(sys.argv[2]),
     'verify': lambda: verify(sys.argv[2])}[sys.argv[1]]()
