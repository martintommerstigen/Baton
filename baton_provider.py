"""One-shot provider client for Baton; no automatic dispatch or Core writes."""
import argparse
import json
import os
import sys
import urllib.request
import uuid

PROVIDERS = {
    'gemini': ('https://generativelanguage.googleapis.com/v1beta/openai/chat/completions', 'GEMINI_API_KEY'),
    'deepseek': ('https://api.deepseek.com/chat/completions', 'DEEPSEEK_API_KEY'),
}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def prepare(provider, model, prompt):
    if not model.strip() or not prompt.strip() or len(prompt.encode('utf-8')) > 16000:
        raise ValueError('Nonempty model and prompt (max 16000 UTF-8 bytes) required')
    return {'provider': provider, 'request_id': str(uuid.uuid4()), 'payload': {
        'model': model, 'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 512, 'stream': False}}


def call(plan, *, allow_cost=False, opener=None):
    if not allow_cost:
        raise ValueError('Explicit cost and data-transfer approval required')
    url, env = PROVIDERS[plan['provider']]
    key = os.environ.get(env)
    if not key:
        raise ValueError(env + ' is not configured')
    req = urllib.request.Request(url, data=json.dumps(plan['payload']).encode(),
                                 headers={'Authorization': 'Bearer ' + key,
                                          'Content-Type': 'application/json'}, method='POST')
    opener = opener or urllib.request.build_opener(NoRedirect()).open
    # One request only. Failure/timeout may have consumed quota; never retry here.
    with opener(req, timeout=45) as response:
        raw = response.read(1000001)
    if len(raw) > 1000000:
        raise ValueError('Response exceeds limit')
    result = json.loads(raw)
    choice = result['choices'][0]
    answer = choice['message'].get('content')
    if choice.get('finish_reason') != 'stop' or not isinstance(answer, str) or not answer.strip():
        raise ValueError('No complete text answer')
    return {'status': 'model_response', 'provider': plan['provider'],
            'request_id': plan['request_id'], 'provider_response_id': result.get('id'),
            'model': result.get('model'), 'text': answer, 'usage': result.get('usage')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('provider', choices=PROVIDERS)
    p.add_argument('--model', required=True)
    p.add_argument('--allow-cost-and-transfer', action='store_true')
    args = p.parse_args()
    try:
        plan = prepare(args.provider, args.model, sys.stdin.read(16001))
        if not args.allow_cost_and_transfer:
            result = {'status': 'prepared_not_sent', **plan}
        else:
            result = call(plan, allow_cost=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        # Avoid echoing provider error bodies, headers, tokens or prompt data.
        print('No confirmed answer: ' + type(error).__name__, file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
