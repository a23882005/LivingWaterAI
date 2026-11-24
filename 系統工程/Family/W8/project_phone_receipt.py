"""Forward Joseph's signed phone receipt to the original pending session."""
import json
import re


def finish_phone_receipt(session, response):
    """Accept the native MCP result, its JSON text, or its structured payload."""
    if isinstance(response, str):
        response = json.loads(response)
    if not isinstance(response, dict) or response.get("isError"):
        raise ValueError("PHONE_TOOL_RESULT_REQUIRED")
    if "structuredContent" in response:
        response = response["structuredContent"]
    elif "content" in response:
        parts = response["content"]
        if (not isinstance(parts, list) or len(parts) != 1
                or not isinstance(parts[0], dict) or parts[0].get("type") != "text"):
            raise ValueError("PHONE_TOOL_RESULT_REQUIRED")
        response = json.loads(parts[0]["text"])
    if not isinstance(response, dict) or response.get("status") != "verified":
        raise ValueError("VERIFIED_PHONE_RECEIPT_REQUIRED")
    if "proof_groups" in response:
        groups = response["proof_groups"]
        if (not isinstance(groups, list) or len(groups) != 8
                or not all(isinstance(part, str) and re.fullmatch(r"[0-9a-f]{8}", part)
                           for part in groups)):
            raise ValueError("PHONE_RECEIPT_GROUPS_INCOMPLETE")
        response = {**response, "proof": "".join(groups)}
    return session.mobile_finish(response)
