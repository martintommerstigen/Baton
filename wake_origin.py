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
    if hasattr(driver, 'is_generating') and driver.is_generating(source_chat):
        raise RuntimeError('Source assistant response is still generating')
    text=driver.read_assistant_turn(source_chat,source_turn_id)
    if not source_requested_wake(text,target_chat,message_id):
        raise PermissionError("Source assistant turn did not request this exact wake")
    return True

def discover_source_turn(driver, source_chat, target_chat, message_id):
    """Find a unique assistant turn containing the exact wake request.

    No user message, quoted sender name or Baton queue receipt counts.
    """
    if hasattr(driver, 'is_generating') and driver.is_generating(source_chat):
        return None
    matches=[]
    for turn_id in driver.list_assistant_turn_ids(source_chat):
        if source_requested_wake(driver.read_assistant_turn(source_chat,turn_id),
                                 target_chat,message_id):
            matches.append(turn_id)
    if len(matches)>1:
        raise RuntimeError("Ambiguous source wake requests")
    return matches[0] if matches else None

def guarded_source_broker_request(driver, source_chat, source_turn_id,
                                  target_chat, message_id, broker_request):
    """Revalidate A's *current* assistant command around each B5 operation.

    The initial check in execute_once is not sufficient: A can change while
    the UI is preparing a B submission. This guard closes mutations during
    admit/begin_click, but cannot eliminate a final post-check-to-click race.
    A broker response remains admission, never proof of ChatGPT authorship.
    """
    if not callable(broker_request):
        raise TypeError("Authenticated broker callback required")

    def request(envelope):
        if (type(envelope) is not dict
                or envelope.get("op") not in ("admit", "begin_click")
                or envelope.get("sender_id") != source_chat
                or envelope.get("origin_turn_id") != source_turn_id
                or envelope.get("conversation_id") != target_chat
                or envelope.get("message_id") != message_id):
            raise PermissionError("Broker envelope disagrees with A source-turn authority")
        verify_source_turn(driver, source_chat, source_turn_id, target_chat, message_id)
        result = broker_request(envelope)
        # If this raises after a broker COMMIT, wake_once preserves uncertainty;
        # never reissue the same message ID as an automatic retry.
        verify_source_turn(driver, source_chat, source_turn_id, target_chat, message_id)
        return result

    return request
