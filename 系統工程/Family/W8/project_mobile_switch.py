"""Start the actual mobile session before offering to switch conversations."""


def route_mobile_switch(session, action, page, *, choice=None):
    """Use only the current native register and this conversation's controller.

    A choice that arrives before a real prompt, or after its register changed,
    cannot authorize replacing the other conversation. The caller executes
    PREPARE_ACCOUNT_DB immediately through the existing account/mobile steps.
    """
    if choice is not None and type(choice) is not bool:
        raise ValueError("INVALID_SWITCH_CHOICE")
    if choice is False:
        if session.stage == "AWAIT_SWITCH":
            return session.choose_switch(False)
        if session.stage in ("PREPARE_ACCOUNT_DB", "AWAIT_PASSWORD"):
            session.cancel()
            return "CANCELLED"
        return "CANCELLED" if session.stage == "IDLE" else session.stage
    if session.stage == "IDLE":
        return session.begin(action, page)
    if session.stage != "AWAIT_SWITCH" or choice is None:
        return session.stage
    current = session._snapshot(page)
    if current.revision != session._base.revision:
        original = session.pending_action
        session.cancel()
        return session.begin(original, page)
    return session.choose_switch(True)
