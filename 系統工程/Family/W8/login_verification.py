"""On-demand mobile tool adapter. The approved controller alone verifies the proof."""
import re
from urllib.parse import urlsplit


class MobileVerification:
    def __init__(self, *, origin, begin_tool, check_tool):
        parts = urlsplit(origin)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.path not in ("", "/") or parts.query or parts.fragment):
            raise ValueError("INVALID_VERIFIER_ORIGIN")
        self.origin = origin.rstrip("/")
        self.begin_tool = begin_tool
        self.check_tool = check_tool
        self.clear()

    def clear(self):
        self.request_id = None
        self.url = None

    def start(self, session):
        request = session.mobile_begin()
        key = request["request_id"]
        if not re.fullmatch("[a-f0-9]{64}", key):
            raise ValueError("INVALID_MOBILE_REQUEST_ID")
        if key != self.request_id or not self.url:
            answer = self.begin_tool(**request)
            url = answer.get("url", "")
            match = re.fullmatch(re.escape(self.origin) + "/verify/([a-f0-9]{64})", url)
            if answer.get("request_id") != key or not match or match[1] == key:
                raise ValueError("INVALID_MOBILE_TOOL_LINK")
            self.request_id, self.url = key, url
        return {"status": "AWAIT_VERIFICATION", "url": self.url}

    def poll(self, session, notification_id=None):
        if notification_id is not None and notification_id != self.request_id:
            return {"status": "UNRELATED_NOTIFICATION"}
        if not self.request_id:
            return self.start(session)
        current = session.mobile_begin()
        if current["request_id"] != self.request_id:
            return self.start(session)
        receipt = self.check_tool(request_id=self.request_id)
        if receipt.get("request_id") != self.request_id:
            raise ValueError("MOBILE_RECEIPT_MISMATCH")
        status = receipt.get("status")
        if status == "verified":
            session.mobile_finish(receipt)
            self.clear()
            return {"status": "READBACK_LOGIN"}
        if status == "expired":
            # The approved session rotates on its own expiry, never use this receipt.
            return {"status": "VERIFICATION_EXPIRED"}
        if status in ("locked", "wrong", "pending"):
            return {"status": "VERIFICATION_" + status.upper(), "url": self.url}
        if status == "cancelled":
            return {"status": "CANCELLED"}
        raise ValueError("UNKNOWN_MOBILE_TOOL_RESULT")
