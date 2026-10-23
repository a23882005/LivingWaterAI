"""Publish only Family informational pages; never touch runtime or private data."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request

NAMES = ('index.html', 'privacy.html', 'terms.html')
SCHEMA = 'family-branding-v1'


def validate(folder):
    from html.parser import HTMLParser
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []
        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                self.links.append(dict(attrs).get('href', ''))
            if tag in ('script', 'iframe', 'form'):
                raise ValueError('Public pages must be static information only')
    for name in NAMES:
        page = folder / name
        assert not page.is_symlink() and page.is_file()
        data = page.read_text(encoding='utf-8')
        assert '<html lang="zh-Hant">' in data and 'Family-Drive' in data
        parser = Links()
        parser.feed(data)
        assert all(n in parser.links for n in NAMES)
        for link in parser.links:
            assert link in NAMES or link.startswith(('https://', 'mailto:'))
    return {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in NAMES}


def build():
    source = Path(__file__).resolve().parents[1] / 'public_branding'
    manifest = {'schema': SCHEMA, 'files': validate(source)}
    stage = Path('build/family-branding/private')
    stage.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        shutil.copyfile(source / name, stage / name)
    (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copyfile(__file__, stage / 'publish_branding.py')
    print(json.dumps(manifest))


def install(root):
    root = Path(root).absolute()
    assert root.name == 'public_html' and root.is_dir() and not root.is_symlink()
    source = Path(__file__).resolve().parent
    manifest = json.loads((source / 'manifest.json').read_text())
    assert manifest == {'schema': SCHEMA, 'files': validate(source)}
    target = root / 'family-info'
    assert not target.is_symlink()
    backup = None
    if target.exists():
        assert target.is_dir()
        assert {p.name for p in target.iterdir()} == set(NAMES) | {'manifest.json'}
        assert not any(p.is_symlink() for p in target.iterdir())
        old = json.loads((target / 'manifest.json').read_text())
        assert old == {'schema': SCHEMA, 'files': validate(target)}, 'Unmanaged or changed target'
        backups = root.parent / '.family-branding-backups'
        assert not backups.is_symlink()
        backups.mkdir(mode=0o700, exist_ok=True)
        os.chmod(backups, 0o700)
        backup = Path(tempfile.mkdtemp(prefix='snapshot-', dir=backups)) / 'family-info'
        shutil.copytree(target, backup)
        for item in backup.rglob('*'):
            os.chmod(item, 0o700 if item.is_dir() else 0o600)
        os.chmod(backup, 0o700)
    staging = Path(tempfile.mkdtemp(prefix='.branding-', dir=root.parent))
    try:
        for name in NAMES + ('manifest.json',):
            shutil.copyfile(source / name, staging / name)
            os.chmod(staging / name, 0o644)
        os.chmod(staging, 0o755)
        target.mkdir(mode=0o755, exist_ok=True)
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
    print('BRANDING_INSTALL_PASS')


def verify(base):
    source = Path(__file__).resolve().parents[1] / 'public_branding'
    expected = validate(source)
    results = []
    for name in NAMES:
        url = base.rstrip('/') + '/family-info/' + ('' if name == 'index.html' else name)
        request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            assert response.status == 200
            assert response.url.startswith(base.rstrip('/') + '/family-info/')
            assert 'text/html' in response.headers.get('Content-Type', '')
        assert hashlib.sha256(body).hexdigest() == expected[name], name
        body.decode('utf-8')
        results.append({'url': url, 'http_status': 200, 'sha256': expected[name]})
    print(json.dumps({'status': 'PASS', 'pages': results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    {'build': build, 'install': lambda: install(sys.argv[2]),
     'verify': lambda: verify(sys.argv[2])}[sys.argv[1]]()
