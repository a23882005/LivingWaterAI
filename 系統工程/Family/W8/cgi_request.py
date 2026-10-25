"""Single-request CGI bridge from trusted PHP to the private W8 OAuth/router.

No bearer, cookie, response payload, file IDs, or Google secrets are logged.
Production family databases remain read-only for exposed W8 portfolio tools.
"""
import base64
import json
from pathlib import Path
import sys

from private_family_service import load_official_router


def main():
    try:
        b = sys.stdin.buffer.read(16385)
        if len(b) > 16384:
            raise ValueError("REQUEST_TOO_LARGE")
        req = json.loads(b.decode("utf-8"))
        if not isinstance(req, dict) or set(req) != {"method", "path", "headers", "body", "peer"}:
            raise ValueError("INVALID_REQUEST")
        if (req["method"] not in ("GET", "POST")
            or not isinstance(req["path"], str) or len(req["path"]) > 10000
            or not req["path"].startswith("/family-connect")
            or not isinstance(req["headers"], dict)
            or not isinstance(req["peer"], str)
            or not isinstance(req["body"], str)):
            raise ValueError("INVALID_REQUEST")
        raw = base64.b64decode(req["body"], validate=True)
        if len(raw) > 8192:
            raise ValueError("BODY_TOO_LARGE")
        # All server configuration is private and fixed relative to this script.
        root = Path(__file__).resolve().parents[3] / ".family-b07-service"
        router = load_official_router(root)
        result = router.handle(req["method"], req["path"], req["headers"], raw, req["peer"])
        code, headers, payload = result
        if not isinstance(code, int) or not isinstance(payload, bytes):
            raise ValueError("INVALID_HANDLER_RESPONSE")
        response = {"status": code, "headers": list(headers),
                    "body": base64.b64encode(payload).decode("ascii")}
    except Exception:
        # Never expose secrets or paths from provider exceptions.
        response = {"status": 503, "headers": [["Content-Type", "application/json"],
                    ["Cache-Control", "no-store"]],
                    "body": base64.b64encode(b'{"error":"SERVICE_RETRY"}').decode("ascii")}
    sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
