import hashlib
import json
import pytest
from pathlib import Path
from copy import deepcopy
import shutil
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


def test_selected_feed_uses_original_reader_without_replacing_default(tmp_path):
    folder=tmp_path/'系統工程/總經V70';folder.mkdir(parents=True)
    reader=Path(__file__).resolve().parents[4]/'系統工程/總經V70/P70-5.py'
    shutil.copyfile(reader,folder/'P70-5.py')
    payload={'schema':'V70.3/family-macro-feed-v3','asOf':'2026-10-20T00:00:00Z',
        'verification':{'ready':True},'indicators':{'m12':{'value':100}}}
    default=folder/'V70_macro_latest.json';default.write_text(json.dumps(payload));before=default.read_bytes()
    selected=tmp_path/'selected-feed.json';other=deepcopy(payload);other['indicators']['m12']['value']=105
    selected.write_text(json.dumps(other))
    spec={'schema_version':'Family.W5.VerifiedMacroFeedSource.v1','local_path':str(selected),
        'sha256':hashlib.sha256(selected.read_bytes()).hexdigest()}
    from family_input import digest
    result=read_macro_snapshot(tmp_path,source_commit='synthetic',capture_bound=True,source=spec)
    assert result['payload']==other
    assert result['capture_receipt']['source_selection_digest']==digest(spec)
    assert result['source_sha256']==spec['sha256']
    assert default.read_bytes()==before
    selected.write_text('{}')
    with pytest.raises(InputError,match='MACRO_FEED_SOURCE_CHANGED'):
        read_macro_snapshot(tmp_path,source_commit='synthetic',source=spec)


def test_source_selection_cannot_be_declared_when_reader_returned_another_feed(tmp_path):
    _,default=source(tmp_path)
    selected=tmp_path/'different.json';selected.write_text(json.dumps({'asOf':'2026-10-21','other':True}))
    spec={'schema_version':'Family.W5.VerifiedMacroFeedSource.v1','local_path':str(selected),
        'sha256':hashlib.sha256(selected.read_bytes()).hexdigest()}
    with pytest.raises(InputError,match='SELECTED_SOURCE_MISMATCH'):
        read_macro_snapshot(tmp_path,source_commit='synthetic',source=spec)
