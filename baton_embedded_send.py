"""Guarded send helper for Baton embedded ChatGPT.

Only the Qt embedded page may invoke this, after the target conversation URL
has been verified. The script checks the composer and send control before
dispatching; DOM changes may require maintenance.
"""
from baton_chatgpt_view import is_chatgpt_conversation_url

def prepare_send_script(message):
    """Insert into the visible, editable ChatGPT composer; never replace a draft."""
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        raise ValueError("invalid message")
    import json
    payload = json.dumps(message)
    return """(() => {
      const message = %s;
      const selectors = [
        '#prompt-textarea',
        '[data-testid="composer-input"]',
        '.ProseMirror[contenteditable]',
        '[role="textbox"][contenteditable]',
        'form [contenteditable]',
        'form textarea'
      ];
      const seen = new Set();
      let editor = null;
      for (const selector of selectors) {
        for (const item of document.querySelectorAll(selector)) {
          if (seen.has(item)) continue;
          seen.add(item);
          if (item.closest('[data-message-author-role]')) continue;
          const editable = item.tagName === 'TEXTAREA' || item.isContentEditable;
          if (!editable) continue;
          const rect = item.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0) continue;
          if (getComputedStyle(item).visibility === 'hidden') continue;
          editor = item;
          break;
        }
        if (editor) break;
      }
      if (!editor) {
        const n = document.querySelectorAll('[contenteditable],textarea').length;
        return {ok:false,reason:'composer-not-found;editor-candidates='+n};
      }
      const textarea = editor.tagName === 'TEXTAREA';
      const previous = textarea ? editor.value : (editor.innerText || editor.textContent || '');
      if (previous.trim()) return {ok:false,reason:'composer-not-empty'};
      editor.focus();
      if (textarea) {
        const descriptor = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value');
        if (!descriptor || !descriptor.set) return {ok:false,reason:'textarea-setter-unavailable'};
        descriptor.set.call(editor, message);
        editor.dispatchEvent(new Event('input', {bubbles:true}));
      } else {
        const selection = window.getSelection();
        if (!selection) return {ok:false,reason:'selection-unavailable'};
        const range = document.createRange();
        range.selectNodeContents(editor);
        selection.removeAllRanges();
        selection.addRange(range);
        if (!document.execCommand('insertText', false, message))
          return {ok:false,reason:'insert-failed'};
        editor.dispatchEvent(new InputEvent('input', {bubbles:true,inputType:'insertText',data:message}));
      }
      const current = textarea ? editor.value : (editor.innerText || editor.textContent || '');
      const normalize = value => value.replace(/\\s+/g,' ').trim();
      if (normalize(current) !== normalize(message))
        return {ok:false,reason:'composer-insertion-not-verified'};
      return {ok:true,reason:'prepared'};
    })()""" % payload


def send_click_script(expected_message=None):
    """Only click an enabled send control when the expected draft is still present."""
    import json
    expected = json.dumps(expected_message)
    return """(() => {
      const expected = %s;
      if (expected !== null) {
        const editor = document.querySelector('#prompt-textarea')
          || document.querySelector('[data-testid="composer-input"]')
          || document.querySelector('.ProseMirror[contenteditable]')
          || document.querySelector('[role="textbox"][contenteditable]')
          || document.querySelector('form textarea');
        if (!editor) return {ok:false,reason:'composer-lost-before-send'};
        const actual = editor.tagName === 'TEXTAREA' ? editor.value : (editor.innerText || editor.textContent || '');
        const normalize = value => value.replace(/\\s+/g,' ').trim();
        if (normalize(actual) !== normalize(expected))
          return {ok:false,reason:'composer-changed-before-send'};
      }
      const selectors = [
        'button[data-testid="send-button"]',
        'button[data-testid="composer-send-button"]',
        'button[aria-label="Send prompt"]',
        'button[aria-label="Send message"]',
        'form button[type="submit"]'
      ];
      let button = null;
      for (const selector of selectors) {
        const candidate = document.querySelector(selector);
        if (candidate && candidate.getBoundingClientRect().width > 0) {
          button = candidate;
          break;
        }
      }
      if (!button || button.disabled || button.getAttribute('aria-disabled') === 'true')
        return {ok:false,reason:'send-not-ready'};
      button.click();
      return {ok:true,reason:'clicked-not-delivery-proof'};
    })()""" % expected


def may_send(url,chat_id):
    return is_chatgpt_conversation_url(url,chat_id)
