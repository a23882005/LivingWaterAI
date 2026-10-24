"""Synthetic tests of the exact approved v1.11 login and menu 02 seam."""
import importlib.util
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import joseph_login
from joseph_read_entry import read_my_data


@pytest.fixture
def setup(tmp_path, monkeypatch):
    clock = SimpleNamespace(wall=10000, mono=100)
    monkeypatch.setattr(joseph_login, 'time', SimpleNamespace(
        time=lambda: clock.wall, monotonic=lambda: clock.mono))
    path = tmp_path / 'synthetic.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE account(user_id,password_shift,enabled,must_change,credential_until,blocked_until)')
        db.execute('INSERT INTO account VALUES(?,?,1,0,NULL,0)',
                   ('JO', ''.join(chr(ord(c)+1+i%4) for i,c in enumerate('synthetic-only'))))
    return joseph_login.JosephLogin(path), path, clock


def test_success_and_reuse_do_not_extend_deadline(setup):
    auth, _, clock = setup
    assert auth.login('JO', 'synthetic-only')['expires_at'] == 24400
    clock.wall += 30; clock.mono += 30
    assert auth.require_login() == 'JO'
    assert auth.expires_at == 24400


@pytest.mark.parametrize('user,password', [('JO','wrong'), ('other','synthetic-only'), ('JO',''), ('JO',None)])
def test_rejected_login_clears_prior_session(setup, user, password):
    auth, _, _ = setup
    auth.login('JO', 'synthetic-only')
    with pytest.raises(PermissionError): auth.login(user, password)
    with pytest.raises(PermissionError): auth.require_login()


@pytest.mark.parametrize('field,value', [('enabled',0),('must_change',1),('credential_until',10000),('blocked_until',10001)])
def test_account_restrictions(setup, field, value):
    auth, path, _ = setup
    with sqlite3.connect(path) as db:
        db.execute('UPDATE account SET '+field+'=?', (value,))
    with pytest.raises(PermissionError): auth.login('JO', 'synthetic-only')


@pytest.mark.parametrize('timer', ['wall','mono'])
def test_exact_four_hour_boundary(setup, timer):
    auth, _, clock = setup
    auth.login('JO', 'synthetic-only')
    setattr(clock, timer, getattr(clock,timer)+14400)
    with pytest.raises(PermissionError): auth.require_login()


def test_logout_and_new_instance_require_login(setup):
    auth, path, _ = setup
    auth.login('JO', 'synthetic-only')
    with pytest.raises(PermissionError): joseph_login.JosephLogin(path).require_login()
    auth.logout()
    with pytest.raises(PermissionError): auth.require_login()


def test_read_denied_before_private_file_open(setup):
    auth, _, _ = setup
    with pytest.raises(PermissionError): read_my_data(auth, '/does-not-exist.db')


def test_reader_identity_is_fixed(setup):
    auth, _, _ = setup
    auth.login('JO', 'synthetic-only')
    seen = {}
    def reader(path, *, expected_client_id):
        seen.update(path=path, client=expected_client_id)
        return 'OK'
    assert auth.read_progress('test.db', reader) == 'OK'
    assert seen['client'] == 'fam_2c96026b72544e828b98be640399432e'


def test_real_reader_rejects_wrong_identity(setup, tmp_path):
    auth, _, _ = setup
    auth.login('JO', 'synthetic-only')
    path=tmp_path/'wrong-person.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE family_member_identity(client_id)')
        db.execute("INSERT INTO family_member_identity VALUES('other-family')")
    with pytest.raises(ValueError, match='CLIENT_MISMATCH'): read_my_data(auth,path)
