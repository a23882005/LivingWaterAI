import hashlib
import json
import pytest
from market_bridge import read_macro_snapshot
from family_input import InputError


def source(tmp_path, mutation=''):
    folder=tmp_path/'系統工程/總經V70'
    folder.mkdir(parents=True)
    feed=folder/'V70_macro_latest.json'
    feed.write_text(json.dumps({'asOf':'2026-10-20', 'quality':{'status':'READY'}}))
    reader=folder/'P70-5.py'
    reader.write_text("import json\ndef read_macro(root):\n    p=root/'系統工程/總經V70/V70_macro_latest.json'\n    raw=json.loads(p.read_text())\n"+mutation+"    return raw\n")
    return reader,feed


def test_preserves_payload_and_hashes(tmp_path):
    reader,feed=source(tmp_path)
    result=read_macro_snapshot(tmp_path,source_commit='synthetic')
    assert result['payload']==json.loads(feed.read_text())
    assert result['source_sha256']==hashlib.sha256(feed.read_bytes()).hexdigest()
    assert result['reader_sha256']==hashlib.sha256(reader.read_bytes()).hexdigest()


@pytest.mark.parametrize('mutation', [
    "    p.write_text('{}')\n",
    "    from pathlib import Path\n    Path(__file__).write_text('# changed')\n",
])
def test_source_mutation_rejected(tmp_path,mutation):
    source(tmp_path,mutation)
    with pytest.raises(InputError,match='MACRO_SOURCE_CHANGED'):
        read_macro_snapshot(tmp_path,source_commit='synthetic')
