"""Native Google Docs calls scoped to one household's registered document.

The execution host supplies the actual tool transports and the official project
binding. A menu payload, chat text or remembered tool response is not a transport.
"""


class FamilyRegistration:
    def __init__(self, account, document_id, *, get_document, batch_update_document):
        if not account or not document_id:
            raise ValueError("REGISTRATION_BINDING_REQUIRED")
        self.account = account
        self.document_id = document_id
        self.get_document = get_document
        self.batch_update_document = batch_update_document

    def _read(self, account, fields):
        if account != self.account:
            raise PermissionError("REGISTRATION_ACCOUNT_MISMATCH")
        doc = self.get_document(document_id=self.document_id, fields=fields)
        if not isinstance(doc, dict) or doc.get("documentId") != self.document_id:
            raise RuntimeError("REGISTRATION_DOCUMENT_MISMATCH")
        if not isinstance(doc.get("revisionId"), str) or not doc["revisionId"].strip():
            raise RuntimeError("REGISTRATION_REVISION_MISSING")
        return doc

    def read_revision(self, account):
        return self._read(account, "documentId,revisionId")["revisionId"]

    def release(self, account, expected_revision):
        """Release only the bound revision. A replaced session is already gone."""
        if not isinstance(expected_revision, str) or not expected_revision.strip():
            raise ValueError("BOUND_LOGIN_REVISION_REQUIRED")
        fields = "documentId,revisionId,tabs(tabProperties(tabId),documentTab(body(content)))"
        doc = self._read(account, fields)
        if doc["revisionId"] != expected_revision:
            return
        tabs = doc.get("tabs") or []
        if len(tabs) != 1 or not tabs[0].get("tabId"):
            raise RuntimeError("REGISTRATION_TAB_UNAVAILABLE")
        blocks = (tabs[0].get("body") or {}).get("content") or []
        if not blocks or not isinstance(blocks[-1].get("endIndex"), int):
            raise RuntimeError("REGISTRATION_BODY_UNAVAILABLE")
        end = blocks[-1]["endIndex"] - 1
        if end < 1:
            raise RuntimeError("REGISTRATION_BODY_INVALID")
        if end == 1:
            return
        reply = None
        try:
            reply = self.batch_update_document(document_id=self.document_id,
                write_control={"requiredRevisionId": expected_revision},
                requests=[{"deleteContentRange": {"range": {
                    "tabId": tabs[0]["tabId"], "startIndex": 1, "endIndex": end}}}])
        except (OSError, RuntimeError, ValueError):
            # Timeout and a competing switch have the same safe recovery:
            # inspect the same document before making any decision.
            pass
        after = self._read(account, fields)
        if after["revisionId"] == expected_revision:
            raise RuntimeError("REGISTRATION_RELEASE_UNCONFIRMED")
        written_revision = (reply.get("writeControl") or {}).get("requiredRevisionId") if isinstance(reply, dict) else None
        if written_revision == after["revisionId"]:
            tabs = after.get("tabs") or []
            if len(tabs) != 1 or tabs[0].get("tabId") != doc["tabs"][0]["tabId"]:
                raise RuntimeError("REGISTRATION_RELEASE_UNCONFIRMED")
            blocks = (tabs[0].get("body") or {}).get("content") or []
            if not blocks or blocks[-1].get("endIndex") != 2:
                raise RuntimeError("REGISTRATION_RELEASE_UNCONFIRMED")
