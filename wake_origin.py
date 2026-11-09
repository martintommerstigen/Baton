"""Read-only proof that an existing source chat requested a specific wake.

This is *UI provenance*, not cryptographic identity or Baton forum authorship.
The operator still supplies an allowlisted source tab and authorizes the action.
"""
from chatgpt_ui_driver import marker_for

def source_requested_wake(reply_text, target_chat, message_id):
    """Accept exactly one standalone command in a verified assistant turn."""
    if not isinstance(reply_text, str) or not reply_text.strip():
        return False
    marker_for(message_id)
    expected=f"BATON_WAKE {target_chat} {message_id}"
    # An example or quoted command inside a longer answer is NOT consent.
    return reply_text.strip()==expected

def verify_source_turn(driver, source_chat, source_turn_id, target_chat, message_id):
    """Fail closed if the source assistant turn is missing or not an exact request."""
    if not source_turn_id:
        raise ValueError("Source assistant turn ID required")
    text=driver.read_assistant_turn(source_chat,source_turn_id)
    if not source_requested_wake(text,target_chat,message_id):
        raise PermissionError("Source assistant turn did not request this exact wake")
    return True

def discover_source_turn(driver, source_chat, target_chat, message_id):
    """Find a unique assistant turn containing the exact wake request.

    No user message, quoted sender name or Baton queue receipt counts.
    """
    matches=[]
    for turn_id in driver.list_assistant_turn_ids(source_chat):
        if source_requested_wake(driver.read_assistant_turn(source_chat,turn_id),
                                 target_chat,message_id):
            matches.append(turn_id)
    if len(matches)>1:
        raise RuntimeError("Ambiguous source wake requests")
    return matches[0] if matches else None
