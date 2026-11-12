"""Read-only DOM observation for existing ChatGPT conversations.

Observations are evidence of a locally rendered page, not server persistence,
cryptographic sender identity, model comprehension or continuing personhood.
Never promote a substring match or an unrelated later reply to a receipt.
"""
import json


def inspect_delivery_script(message):
    """Only a UNIQUE exact user turn and its immediate assistant reply can match.

    ChatGPT's rendered DOM may normalize whitespace. This uses equal normalized
    *whole-turn* text, never substring inclusion; a manual quotation or later
    unrelated assistant reply must not be counted as the transport result.
    """
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        raise ValueError("invalid message")
    payload = json.dumps(message)
    return """(() => {
      const expected = %s;
      const turns = Array.from(document.querySelectorAll('[data-message-author-role]'));
      const normalized = text => (text || '').replace(/\\s+/g, ' ').trim();
      const needle = normalized(expected);
      const matches = [];
      turns.forEach((turn, index) => {
        if (turn.getAttribute('data-message-author-role') === 'user'
            && normalized(turn.innerText || turn.textContent) === needle)
          matches.push(index);
      });
      const absent = {
        userVisible:false, replyVisible:false, replyComplete:false,
        assistantMessageId:null, assistantText:'', correlation:'none'
      };
      if (matches.length === 0) return {...absent, reason:'exact-user-turn-not-found'};
      if (matches.length !== 1) return {
        ...absent, userVisible:true, correlation:'ambiguous',
        reason:'duplicate-exact-user-turn'
      };
      const reply = turns[matches[0] + 1];
      if (!reply || reply.getAttribute('data-message-author-role') !== 'assistant')
        return {
          ...absent, userVisible:true, reason:'no-adjacent-assistant-turn'
        };
      const replyText = (reply.innerText || reply.textContent || '').slice(0,6000);
      const replyVisible = Boolean(normalized(replyText));
      const assistantMessageId = reply.getAttribute('data-message-id') || null;
      const sameIdCount = assistantMessageId
        ? turns.filter(turn =>
            turn.getAttribute('data-message-author-role') === 'assistant' &&
            turn.getAttribute('data-message-id') === assistantMessageId).length
        : 0;
      const streaming = Boolean(document.querySelector('[data-testid="stop-button"]'));
      const uniqueId = Boolean(assistantMessageId && sameIdCount === 1);
      return {
        userVisible:true, replyVisible,
        replyComplete: Boolean(replyVisible && !streaming && uniqueId),
        assistantMessageId: uniqueId ? assistantMessageId : null,
        assistantText: replyText,
        correlation:'unique-adjacent',
        reason: !replyVisible ? 'empty-reply'
          : streaming ? 'still-generating'
          : !uniqueId ? 'missing-or-duplicate-assistant-id'
          : 'completed-correlated-turn'
      };
    })()""" % payload


def verified_reply_observation(result):
    """Fail closed on absent/ambiguous DOM provenance; caller must not resend."""
    return (
        isinstance(result, dict)
        and result.get("userVisible") is True
        and result.get("replyVisible") is True
        and result.get("replyComplete") is True
        and result.get("correlation") == "unique-adjacent"
        and isinstance(result.get("assistantMessageId"), str)
        and 0 < len(result["assistantMessageId"].strip()) <= 256
    )
