"""Read-only, source-bound DOM observation of an existing ChatGPT reply.

The live QtWebEngine ChatGPT client (verified on Greg 2026-11-12) uses
[data-chatgpt-search-unit-key] and [data-chatgpt-search-message-ids], NOT
[data-message-author-role]. Preserve a fail-closed legacy path for older UIs.
A visible response is evidence of rendered UI, not of learning or continuity.
"""
import json


def inspect_delivery_script(message):
    """Require unique exact user payload and directly adjacent identified reply.

    No substring matching, no later unrelated assistant reply, no guessed IDs.
    Use the native ChatGPT selection-conversation marker to reject redirects.
    """
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        raise ValueError("invalid message")
    script = r"""(() => {
      const expected = __EXPECTED__;
      const absent = {
        userVisible:false, replyVisible:false, replyComplete:false,
        assistantMessageId:null, assistantText:'', correlation:'none'
      };
      const normalized = text => (text || '').replace(/\s+/g, ' ').trim();
      const needle = normalized(expected);
      const units = Array.from(document.querySelectorAll('[data-chatgpt-search-unit-key]'));
      const legacy = Array.from(document.querySelectorAll('[data-message-author-role]'));
      const native = units.length > 0;
      let turns = [];
      if (native) {
        const path = window.location.pathname;
        const expectedId = path.split('/').filter(Boolean).at(-1);
        const markers = new Set(
          Array.from(document.querySelectorAll('[data-chatgpt-selection-conversation-id]'))
          .map(e => e.getAttribute('data-chatgpt-selection-conversation-id'))
          .filter(Boolean)
        );
        if (window.location.protocol !== 'https:' ||
            window.location.hostname !== 'chatgpt.com' ||
            !/^\/c\/[0-9a-f-]{36}$/.test(path) ||
            markers.size !== 1 || !markers.has(expectedId))
          return {...absent, reason:'source-conversation-not-bound'};
        const seen = new Set();
        turns = units.map(unit => {
          const key = unit.getAttribute('data-chatgpt-search-unit-key') || '';
          const role = key.endsWith(':user') ? 'user'
                     : key.endsWith(':assistant') ? 'assistant' : null;
          const ids = [...new Set(
            (unit.getAttribute('data-chatgpt-search-message-ids') || '')
            .split(/\s+/).filter(Boolean)
          )];
          const id = ids.length === 1 ? ids[0] : null;
          let text = '';
          if (role === 'user') {
            const bubble = unit.querySelector('[data-user-message-bubble]');
            text = bubble?.querySelector('.whitespace-pre-wrap')?.innerText
                   || bubble?.innerText || '';
          }
          if (role === 'assistant') {
            const nodes = Array.from(unit.querySelectorAll('[data-markdown-text-style]'));
            const top = nodes.filter(n =>
              !nodes.some(other => other !== n && other.contains(n)));
            text = top.map(n => n.innerText || '').join('\n\n');
          }
          return {role, id, text};
        }).filter(turn => turn.role)
          // Preserve empty-text turns as adjacency barriers. Image-only user
          // turns and unreadable assistant turns must not vanish and make a
          // later unrelated assistant appear adjacent to a Baton request.
          .filter(turn => {
            // Native clients may repeat one logical turn in two DOM fragments.
            // Deduplicate only by a genuine ID, never by message text.
            if (!turn.id) return true;
            const key = turn.role + ':' + turn.id;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
          });
      } else {
        turns = legacy.map(turn => ({
          role:turn.getAttribute('data-message-author-role'),
          id:turn.getAttribute('data-message-id') || null,
          text:turn.innerText || turn.textContent || ''
        }));
      }
      const matches = [];
      turns.forEach((turn, index) => {
        if (turn.role === 'user' && normalized(turn.text) === needle)
          matches.push(index);
      });
      if (matches.length === 0)
        return {...absent, reason:'exact-user-turn-not-found'};
      if (matches.length !== 1)
        return {...absent, userVisible:true, correlation:'ambiguous',
                reason:'duplicate-exact-user-turn'};
      const reply = turns[matches[0] + 1];
      if (!reply || reply.role !== 'assistant')
        return {...absent, userVisible:true, reason:'no-adjacent-assistant-turn'};
      const replyText = reply.text.slice(0,6000);
      const replyVisible = Boolean(normalized(replyText));
      const id = reply.id;
      const idUnique = typeof id === 'string' && id.length > 0 && id.length <= 256
            && turns.filter(t => t.role === 'assistant' && t.id === id).length === 1;
      const streaming = Boolean(document.querySelector('[data-testid="stop-button"]')) ||
          Array.from(document.querySelectorAll('button')).some(
            b => ['Stop','Stopp','Stop generating'].includes(b.getAttribute('aria-label')));
      return {
        userVisible:true, replyVisible,
        replyComplete:Boolean(replyVisible && idUnique && !streaming),
        assistantMessageId:idUnique ? id : null,
        assistantText:replyText,
        correlation:'unique-adjacent',
        schema:native ? 'native' : 'legacy',
        reason: !replyVisible ? 'empty-reply'
             : streaming ? 'still-generating'
             : !idUnique ? 'missing-or-duplicate-assistant-id'
             : 'completed-correlated-turn'
      };
    })()"""
    return script.replace("__EXPECTED__", json.dumps(message, ensure_ascii=True))


def verified_reply_observation(result):
    """Reject all unverifiable/ambiguous response evidence; never auto-resend."""
    return (
        isinstance(result, dict)
        and result.get("userVisible") is True
        and result.get("replyVisible") is True
        and result.get("replyComplete") is True
        and result.get("correlation") == "unique-adjacent"
        and isinstance(result.get("assistantMessageId"), str)
        and 0 < len(result["assistantMessageId"].strip()) <= 256
    )
