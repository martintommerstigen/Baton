"""Domain-separated server admission receipt for the one-shot HTTP client.

The server proves possession of the sender's HMAC key *after* durable local
admission. This is NOT a ChatGPT delivery receipt or a proof of source
completeness. A nonce prevents reusing a signed receipt for a different send.
"""
import hashlib
import hmac
import re

from remote_security.envelope_gate import Gate

_NONCE = re.compile(r'[0-9a-f]{32}')


def admission_mac(sender_key, nonce, envelope, state):
    if not isinstance(sender_key, bytes) or len(sender_key) < 32:
        raise ValueError('invalid receipt key')
    if not isinstance(nonce, str) or not _NONCE.fullmatch(nonce):
        raise ValueError('invalid receipt nonce')
    if state != 'accepted_not_delivered':
        raise ValueError('only durable admission can be attested')
    raw = (b'BATON-REMOTE-ADMISSION-v1' + bytes([0]) + bytes.fromhex(nonce)
           + bytes([0]) + Gate.canonical(envelope) + bytes([0])
           + state.encode('ascii'))
    return hmac.new(sender_key, raw, hashlib.sha256).hexdigest()
