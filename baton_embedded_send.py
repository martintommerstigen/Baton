"""Guarded send helper for Baton embedded ChatGPT.

Only the Qt embedded page may invoke this, after the target conversation URL
has been verified. The script checks the composer and send control before
dispatching; DOM changes may require maintenance.
"""
from baton_chatgpt_view import is_chatgpt_conversation_url

def prepare_send_script(message):
    if not isinstance(message,str) or not message.strip() or len(message)>4000:
        raise ValueError("invalid message")
    import json
    payload=json.dumps(message)
    return """(() => {
      const message = %s;
      const editor = document.querySelector('#prompt-textarea[contenteditable="true"]')
        || document.querySelector('[data-testid="composer-input"][contenteditable="true"]');
      if (!editor) return {ok:false,reason:'composer-not-found'};
      if ((editor.innerText || '').trim()) return {ok:false,reason:'composer-not-empty'};
      editor.focus();
      const selection=window.getSelection();
      const range=document.createRange();
      range.selectNodeContents(editor); selection.removeAllRanges(); selection.addRange(range);
      if (!document.execCommand('insertText',false,message))
        return {ok:false,reason:'insert-failed'};
      editor.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:message}));
      return {ok:true,reason:'prepared'};
    })()""" % payload

def send_click_script():
    return """(() => {
      const button = document.querySelector('button[data-testid="send-button"]');
      if (!button || button.disabled) return {ok:false,reason:'send-not-ready'};
      button.click();
      return {ok:true,reason:'clicked-not-delivery-proof'};
    })()"""

def may_send(url,chat_id):
    return is_chatgpt_conversation_url(url,chat_id)
