"""Opt-in UI driver for one existing ChatGPT conversation.

The driver operates only on an already-open authenticated Playwright Page.
It does not open a new conversation, authenticate, extract credentials or use
private APIs. DOM selectors must be verified against the live interface.
"""
from dataclasses import dataclass
import re
from urllib.parse import urlparse
from wake_adapter import Observation

CHAT_ID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)
MARKER_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def conversation_id(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ("chatgpt.com", "www.chatgpt.com"):
        raise ValueError("Not an allowed ChatGPT origin")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Unexpected origin credentials or port")
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2 or parts[0] != "c" or not CHAT_ID.fullmatch(parts[1]):
        raise ValueError("Not an existing ChatGPT conversation URL")
    return parts[1].lower()


def marker_for(message_id):
    if not isinstance(message_id, str) or not MARKER_ID.fullmatch(message_id):
        raise ValueError("Invalid message ID")
    return f"[BATON-WAKE:{message_id}]"


@dataclass
class ChatGPTUIDriver:
    page: object
    allowed_conversations: frozenset[str]

    def _check(self, target):
        if target not in self.allowed_conversations:
            raise PermissionError("Conversation not allowlisted")
        if conversation_id(self.page.url) != target:
            raise RuntimeError("Page is not the target existing conversation")

    def submit_once(self, conversation_id, message_id, body):
        self._check(conversation_id)
        marker = marker_for(message_id)
        if not isinstance(body, str) or not body.strip():
            raise ValueError("Nonempty body required")
        if self.page.locator('[data-message-author-role="user"]').filter(has_text=marker).count():
            raise RuntimeError("Marker already present; reconcile without resending")
        editor = self.page.locator("#prompt-textarea")
        if editor.count() != 1 or not editor.is_visible():
            raise RuntimeError("Composer missing or ambiguous")
        if editor.inner_text().strip():
            raise RuntimeError("Composer contains a draft")
        editor.fill(marker + "\n" + body)
        self._check(conversation_id)
        send = self.page.locator('[data-testid="send-button"]')
        if send.count() != 1 or not send.is_enabled():
            raise RuntimeError("Send button missing or disabled; draft left unsent")
        send.click()
        self._check(conversation_id)

    def observe_reply(self, conversation_id, message_id):
        self._check(conversation_id)
        marker = marker_for(message_id)
        turns = self.page.locator("[data-message-author-role]")
        markers = []
        for i in range(turns.count()):
            turn = turns.nth(i)
            if turn.get_attribute("data-message-author-role") == "user" and marker in turn.inner_text():
                markers.append(i)
        if len(markers) != 1:
            return None
        if self.page.locator('[data-testid="stop-button"]').count():
            return None
        # Require the immediate next turn to be an assistant response.
        i = markers[0] + 1
        if i >= turns.count():
            return None
        reply = turns.nth(i)
        if reply.get_attribute("data-message-author-role") != "assistant":
            return None
        turn_id = reply.get_attribute("data-message-id")
        if not turn_id or not reply.inner_text().strip():
            return None
        return Observation(conversation_id, turn_id)

    def read_assistant_turn(self, conversation_id, assistant_turn_id):
        self._check(conversation_id)
        if not assistant_turn_id:
            raise ValueError("Missing verified assistant turn ID")
        turns = self.page.locator('[data-message-author-role="assistant"]')
        matches = [turns.nth(i) for i in range(turns.count())
                   if turns.nth(i).get_attribute("data-message-id") == assistant_turn_id]
        if len(matches) != 1:
            raise RuntimeError("Verified assistant turn missing or ambiguous")
        return matches[0].inner_text()
