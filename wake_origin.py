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
    commands=[line.strip() for line in reply_text.splitlines()
              if line.strip().startswith("BATON_WAKE")]
    return commands==[expected]

def verify_source_turn(driver, source_chat, source_turn_id, target_chat, message_id):
    """Fail closed if the source assistant turn is missing or not an exact request."""
    if not source_turn_id:
        raise ValueError("Source assistant turn ID required")
    text=driver.read_assistant_turn(source_chat,source_turn_id)
    if not source_requested_wake(text,target_chat,message_id):
        raise PermissionError("Source assistant turn did not request this exact wake")
    return True
