import io
import json
from pathlib import Path
import sys
import urllib.error
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drive_service_transport import GoogleDriveTransport, ServiceTransportError, NoRedirect

URL = 'https://www.googleapis.com/drive/v3/files/synthetic?alt=media'
class Reply(io.BytesIO):
    status = 200
class Opener:
    def __init__(self, replies): self.replies, self.calls = list(replies), []
    def open(self, request, timeout):
        self.calls.append((request, timeout))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception): raise reply
        return Reply(reply)
TOKEN = b'{"access_token":"synthetic-access","expires_in":3600}'
def transport(opener, clock=lambda: 100):
    return GoogleDriveTransport('id', 'synthetic-secret', 'synthetic-refresh', opener=opener, clock=clock)

def test_token_reuse_and_fixed_refresh_deadline():
    now=[100]; o=Opener([TOKEN,b'{}',b'{}',TOKEN,b'{}']);t=transport(o,lambda:now[0])
    t.call(URL);now[0]=3639;t.call(URL);now[0]=3640;t.call(URL)
    assert len(o.calls)==5
    assert all(timeout==30 for _,timeout in o.calls)
    assert o.calls[1][0].get_header('Authorization')=='Bearer synthetic-access'

@pytest.mark.parametrize('url', ['http://www.googleapis.com/drive/v3/files/a',
    'https://evil.example/drive/v3/files/a', 'https://www.googleapis.com@evil.example/drive/v3/files/a',
    'https://www.googleapis.com/oauth2/a'])
def test_reject_url_before_auth(url):
    o=Opener([])
    with pytest.raises(ValueError):transport(o).call(url)
    assert not o.calls

def test_write_error_redacted_without_retry():
    error=urllib.error.HTTPError(URL,503,'synthetic-secret',{},io.BytesIO(b'synthetic-refresh'))
    o=Opener([TOKEN,error]); t=transport(o)
    with pytest.raises(ServiceTransportError,match='^PROVIDER_HTTP_503$'): t.call(URL,'PATCH',b'data')
    assert len(o.calls)==2

def test_unauthorized_clears_cache_next_call_renews():
    error=urllib.error.HTTPError(URL,401,'private',{},io.BytesIO(b'private'))
    o=Opener([TOKEN,error,TOKEN,b'{}']);t=transport(o)
    with pytest.raises(ServiceTransportError):t.call(URL)
    assert t.token is None
    assert t.call(URL)=={}

def test_no_redirect_and_token_size_limit():
    assert NoRedirect().redirect_request(None,None,302,'',{},'https://evil.example') is None
    with pytest.raises(ServiceTransportError,match='TOO_LARGE'):
        transport(Opener([b'x'*65537])).call(URL)

@pytest.mark.parametrize('response',[b'not JSON', b'{}', b'{"access_token":"bad\\nheader","expires_in":3600}'])
def test_invalid_token_response(response):
    with pytest.raises(ServiceTransportError,match='INVALID_TOKEN_RESPONSE'):transport(Opener([response])).call(URL)
