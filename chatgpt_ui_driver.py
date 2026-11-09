"""Opt-in Playwright UI driver for an EXISTING ChatGPT conversation.

Requires an already authenticated Playwright Page; never creates a conversation,
extracts cookies, uses private APIs or bypasses access controls.
Fail-closed if ChatGPT changes its UI. The local operator must authorize the tab.
"""
from dataclasses import dataclass
import re
from urllib.parse import urlparse
from wake_adapter import Observation

CHAT_ID = re.compile(r'^[0-9a-f]{8}-[0-9a-f-]{8,}$', re.I)

def conversation_id(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('chatgpt.com', 'www.chatgpt.com'):
        raise ValueError('Not an allowed ChatGPT origin')
    parts = parsed.path.strip('/').split('/')
    if len(parts) != 2 or parts[0] != 'c' or not CHAT_ID.fullmatch(parts[1]):
        raise ValueError('Not an existing ChatGPT conversation URL')
    return parts[1]

@dataclass
class ChatGPTUIDriver:
    page: object
    allowed_conversations: frozenset[str]

    def _check(self, target):
        if target not in self.allowed_conversations:
            raise PermissionError('Conversation not allowlisted')
        if conversation_id(self.page.url) != target:
            raise RuntimeError('Page is not the target existing conversation')

    def submit_once(self, conversation_id, message_id, body):
        self._check(conversation_id)
        if not message_id or not body.strip():
            raise ValueError('Message ID and nonempty body required')
        marker = f'[BATON-WAKE:{message_id}]'
        if self.page.get_by_text(marker, exact=False).count():
            raise RuntimeError('Marker already present; reconcile without resending')
        editor = self.page.locator('#prompt-textarea')
        if editor.count() != 1 or not editor.is_visible():
            raise RuntimeError('Composer missing or ambiguous; no send')
        if editor.inner_text().strip():
            raise RuntimeError('Composer contains a draft; no send')
        editor.fill(marker + '\n' + body)
        self._check(conversation_id)
        editor.press('Enter')
        self._check(conversation_id)

    def observe_reply(self, conversation_id, message_id):
        self._check(conversation_id)
        marker = f'[BATON-WAKE:{message_id}]'
        user_turns = self.page.locator('[data-message-author-role="user"]')
        matched = [i for i in range(user_turns.count()) if marker in user_turns.nth(i).inner_text()]
        if len(matched) != 1:
            return None
        if self.page.locator('[data-testid="stop-button"]').count():
            return None
        turns = self.page.locator('[data-message-author-role]')
        seen = False
        for i in range(turns.count()):
            turn = turns.nth(i)
            role = turn.get_attribute('data-message-author-role')
            if role == 'user' and marker in turn.inner_text():
                seen = True
                continue
            if seen and role == 'assistant':
                turn_id = turn.get_attribute('data-message-id')
                if turn_id and turn.inner_text().strip():
                    return Observation(conversation_id, turn_id)
        return None
