"""Bounded Google service transport. Credentials are injected, never logged.

Single host may share a transport between threads. No redirects, no automatic
write retries. B06 journal reconciles uncertain writes. Does not change OAuth
publishing status or turn a testing refresh token into a long-lived token.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

LIMIT = 64 * 1024 * 1024

class ServiceTransportError(RuntimeError):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class GoogleDriveTransport:
    def __init__(self, client_id, client_secret, refresh_token, *, timeout=30,
                 clock=time.monotonic, opener=None):
        if not all(isinstance(x, str) and x for x in (client_id, client_secret, refresh_token)):
            raise ValueError('SERVICE_CREDENTIALS_REQUIRED')
        if not 1 <= timeout <= 60:
            raise ValueError('INVALID_TIMEOUT')
        self.credentials = (client_id, client_secret, refresh_token)
        self.timeout, self.clock = timeout, clock
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.token, self.until, self.lock = None, 0, threading.Lock()

    def _send(self, request, limit):
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    raise ServiceTransportError('PROVIDER_REJECTED')
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise ServiceTransportError('PROVIDER_RESPONSE_TOO_LARGE')
                return data
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            raise ServiceTransportError('PROVIDER_HTTP_' + str(code)) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ServiceTransportError('PROVIDER_UNAVAILABLE') from None

    def _access_token(self):
        with self.lock:
            if self.token and self.clock() < self.until:
                return self.token
            cid, secret, refresh = self.credentials
            body = urllib.parse.urlencode(dict(client_id=cid, client_secret=secret,
                refresh_token=refresh, grant_type='refresh_token')).encode()
            request = urllib.request.Request('https://oauth2.googleapis.com/token', data=body,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
            started = self.clock()
            try:
                value = json.loads(self._send(request, 65536))
                token, ttl = value['access_token'], value['expires_in']
                if (not isinstance(token, str) or not token or '\r' in token or '\n' in token
                    or type(ttl) is not int or ttl <= 60 or ttl > 86400):
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise ServiceTransportError('INVALID_TOKEN_RESPONSE') from None
            self.token, self.until = token, started + ttl - 60
            return token

    def call(self, url, method='GET', data=None, raw=False):
        parts = urllib.parse.urlsplit(url)
        if (parts.scheme != 'https' or parts.netloc != 'www.googleapis.com' or parts.fragment
            or not (parts.path.startswith('/drive/v3/files') or parts.path.startswith('/upload/drive/v3/files'))
            or method not in ('GET', 'POST', 'PATCH', 'DELETE')):
            raise ValueError('DISALLOWED_PROVIDER_REQUEST')
        headers = {'Authorization': 'Bearer ' + self._access_token()}
        if isinstance(data, dict):
            body = json.dumps(data, allow_nan=False).encode()
            headers['Content-Type'] = 'application/json'
        elif isinstance(data, bytes):
            body = data
            headers['Content-Type'] = 'application/octet-stream'
        elif data is None:
            body = None
        else:
            raise ValueError('INVALID_REQUEST_BODY')
        if body is not None and len(body) > LIMIT:
            raise ValueError('REQUEST_TOO_LARGE')
        try:
            result = self._send(urllib.request.Request(url, data=body, headers=headers, method=method), LIMIT)
        except ServiceTransportError as error:
            if str(error) == 'PROVIDER_HTTP_401':
                with self.lock:
                    self.token, self.until = None, 0
            raise
        if raw:
            return result
        try:
            return json.loads(result) if result else {}
        except (ValueError, TypeError):
            raise ServiceTransportError('INVALID_PROVIDER_JSON') from None
