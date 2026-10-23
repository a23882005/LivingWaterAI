import json
import stat
import pytest
from test_private_runtime import config
from private_runtime import provision, read_private
from private_service_config import load_key
from private_entry_config import confirmed_entry, install_entry


def prepared(tmp_path):
    root = tmp_path / 'private'
    provision(root, config(tmp_path))
    return root


def test_install_and_repeat_preserve_runtime_and_identity(tmp_path):
    root = prepared(tmp_path)
    before = read_private(root / 'runtime.json'), load_key(root)
    first = install_entry(root)
    entry = read_private(root / 'entry.json')
    assert install_entry(root) == first
    assert first['public_enabled'] is False
    assert (read_private(root / 'runtime.json'), load_key(root)) == before
    assert json.loads(entry) == confirmed_entry()
    assert stat.S_IMODE((root / 'entry.json').stat().st_mode) == 0o600
    assert entry in [read_private(p) for p in (root / 'backups').glob('entry-*')]


@pytest.mark.parametrize('field,value', [
    ('connection_scope', 'another-device'),
    ('oauth_clients', {'family-chatgpt': ['https://example.com/callback']}),
    ('origin', 'https://example.com')])
def test_existing_registration_never_silently_overwritten(tmp_path, field, value):
    root = prepared(tmp_path)
    install_entry(root)
    changed = confirmed_entry(); changed[field] = value
    (root / 'entry.json').write_text(json.dumps(changed))
    old = read_private(root / 'entry.json')
    with pytest.raises(ValueError, match='ENTRY_MIGRATION_REQUIRED'):
        install_entry(root)
    assert read_private(root / 'entry.json') == old


def test_symlink_entry_rejected_without_touching_destination(tmp_path):
    root = prepared(tmp_path)
    outside = tmp_path / 'outside'; outside.write_text('untouched')
    (root / 'entry.json').symlink_to(outside)
    with pytest.raises(OSError): install_entry(root)
    assert outside.read_text() == 'untouched'


def test_missing_key_does_not_register_client(tmp_path):
    root = prepared(tmp_path)
    (root / 'server.key').unlink()
    with pytest.raises(FileNotFoundError): install_entry(root)
    assert not (root / 'entry.json').exists()


def test_enabled_runtime_rejected(tmp_path):
    root = prepared(tmp_path)
    path = root / 'runtime.json'
    value = json.loads(path.read_text()); value['enabled'] = True
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='NOT_READY_FOR_PUBLIC_ENTRY'):
        install_entry(root)
    assert not (root / 'entry.json').exists()
