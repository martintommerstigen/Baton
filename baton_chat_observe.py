"""Observation helpers for the ChatGPT web view.

Observations from the page are evidence of what Baton rendered locally,
NOT cryptographic proof of remote persistence or independent agent activity.
"""
import json

def inspect_delivery_script(message):
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        raise ValueError("invalid message")
    payload = json.dumps(message)
    return """(() => {
      const expected = %s;
      const turns = Array.from(document.querySelectorAll('[data-message-author-role]'));
      const normalized = text => (text || '').replace(/\\s+/g, ' ').trim();
      const needle = normalized(expected);
      const index = turns.findLastIndex(turn =>
        turn.getAttribute('data-message-author-role') === 'user' &&
        normalized(turn.innerText).includes(needle));
      if (index < 0) return {userVisible:false, replyVisible:false, replyComplete:false};
      const replies = turns.slice(index + 1).filter(turn =>
        turn.getAttribute('data-message-author-role') === 'assistant');
      const reply = replies[replies.length - 1];
      const replyVisible = Boolean(reply && normalized(reply.innerText));
      const streaming = Boolean(document.querySelector('[data-testid="stop-button"]'));
      return {
        userVisible:true,
        replyVisible:replyVisible,
        replyComplete:replyVisible && !streaming,
        assistantMessageId: reply ? (reply.getAttribute('data-message-id') || null) : null
      };
    })()""" % payload
