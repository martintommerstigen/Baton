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
    """Click at most once: require identical draft and an enabled send control.

    ChatGPT changes the submit selector by layout and locale; never use an
    unrelated toolbar button or a Stop/voice action as a fallback.
    """
    import json
    expected = json.dumps(expected_message)
    return """(() => {
      const expected = %s;
      const visible = node => {
        if (!node || !node.isConnected) return false;
        const rect = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        return rect.width > 0 && rect.height > 0
          && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const editorSelectors = [
        '#prompt-textarea', '[data-testid="composer-input"]',
        '.ProseMirror[contenteditable]', '[role="textbox"][contenteditable]',
        'form textarea'
      ];
      let editor = null;
      for (const selector of editorSelectors) {
        editor = Array.from(document.querySelectorAll(selector)).find(node =>
          visible(node) && !node.closest('[data-message-author-role]')
          && (node.isContentEditable || node.tagName === 'TEXTAREA'));
        if (editor) break;
      }
      if (!editor) return {ok:false,reason:'composer-lost-before-send'};
      const actual = editor.tagName === 'TEXTAREA'
        ? editor.value : (editor.innerText || editor.textContent || '');
      const normalize = value => (value || '').replace(/\\s+/g,' ').trim();
      if (expected !== null && normalize(actual) !== normalize(expected))
        return {ok:false,reason:'composer-changed-before-send'};
      const composerForm = editor.closest('form');
      const selectors = [
        'button#composer-submit-button',
        'button[data-testid="send-button"]',
        'button[data-testid="composer-send-button"]',
        'button.composer-submit-btn',
        'button[aria-label="Send prompt"]',
        'button[aria-label="Send message"]',
        'button[aria-label="Send"]',
        'button[aria-label="Send dictated message"]',
        'form[data-chatgpt-composer] button[type="submit"]'
      ];
      // Consider all matching buttons, not the first possibly disabled or
      // hidden match. Prefer the send button in the editor's own form.
      const candidates = [];
      for (const selector of selectors) {
        for (const node of document.querySelectorAll(selector)) {
          if (candidates.includes(node) || !visible(node)) continue;
          if (composerForm && node.closest('form') !== composerForm) continue;
          candidates.push(node);
        }
      }
      // Only the active composer's submit control is an allowed generic
      // fallback; never click arbitrary document-wide submit buttons.
      if (composerForm) {
        for (const node of composerForm.querySelectorAll('button[type="submit"]')) {
          if (visible(node) && !candidates.includes(node))
            candidates.push(node);
        }
      }
      const enabled = candidates.filter(node =>
        !node.disabled && node.getAttribute('aria-disabled') !== 'true'
        && !/stop|dictat|record|microphone|voice/i.test(
          [node.getAttribute('aria-label'), node.getAttribute('data-testid')].join(' ')));
      if (enabled.length !== 1) return {
        ok:false, reason:'send-not-ready',
        detail: 'candidate-count='+candidates.length+' enabled='+enabled.length
      };
      enabled[0].click();
      return {ok:true,reason:'clicked-not-delivery-proof'};
    })()""" % expected


def clear_prepared_script(expected_message):
    """Delete only Baton's exact unsent draft, preserving human edits."""
    import json
    expected = json.dumps(expected_message)
    return """(() => {
      const expected = %s;
      const editor = Array.from(document.querySelectorAll(
        '#prompt-textarea, [data-testid="composer-input"], .ProseMirror[contenteditable], [role="textbox"][contenteditable], form textarea'
      )).find(node => (node.isContentEditable || node.tagName === 'TEXTAREA')
          && node.getBoundingClientRect().width > 0);
      if (!editor) return {ok:false,reason:'no-draft-editor'};
      const isTextArea = editor.tagName === 'TEXTAREA';
      const value = isTextArea ? editor.value : (editor.innerText || editor.textContent || '');
      // Exact match (not whitespace normalization): do not erase an edited draft.
      if (value !== expected) return {ok:false,reason:'draft-was-changed'};
      editor.focus();
      if (isTextArea) {
        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;
        setter.call(editor, '');
        editor.dispatchEvent(new Event('input',{bubbles:true}));
      } else {
        const selection = window.getSelection();
        if (!selection) return {ok:false,reason:'selection-unavailable'};
        const range = document.createRange();
        range.selectNodeContents(editor);
        selection.removeAllRanges();
        selection.addRange(range);
        if (!document.execCommand('delete',false))
          return {ok:false,reason:'draft-clear-failed'};
      }
      const current = isTextArea ? editor.value : (editor.innerText || editor.textContent || '');
      return current.trim() ? {ok:false,reason:'draft-still-present'}
        : {ok:true,reason:'cleared-only-baton-draft'};
    })()""" % expected


def may_send(url,chat_id):
    return is_chatgpt_conversation_url(url,chat_id)
