import concurrent.futures
import os
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from private_service_config import provision_key,load_key

def test_persistent_and_parallel(tmp_path):
    root=tmp_path/'private'
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        keys=list(pool.map(lambda _:provision_key(root),range(8)))
    assert len(set(keys))==1 and len(keys[0])==32
    assert load_key(root)==keys[0]

def test_missing_not_regenerated(tmp_path):
    root=tmp_path/'private';provision_key(root);(root/'server.key').unlink()
    with pytest.raises(FileNotFoundError):load_key(root)

@pytest.mark.parametrize('mode',[0o644,0o666])
def test_public_key_rejected(tmp_path,mode):
    root=tmp_path/'private';provision_key(root);os.chmod(root/'server.key',mode)
    with pytest.raises(ValueError):load_key(root)

def test_corrupt_key_not_replaced(tmp_path):
    root=tmp_path/'private';provision_key(root);(root/'server.key').write_bytes(b'bad')
    with pytest.raises(ValueError):provision_key(root)
    assert (root/'server.key').read_bytes()==b'bad'

def test_symlink_rejected(tmp_path):
    root=tmp_path/'private';provision_key(root);(tmp_path/'link').symlink_to(root)
    with pytest.raises(ValueError):load_key(tmp_path/'link')
    (root/'server.key').unlink();(root/'server.key').symlink_to(tmp_path/'target')
    with pytest.raises(OSError):load_key(root)
