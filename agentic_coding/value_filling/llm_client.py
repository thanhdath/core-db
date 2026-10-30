"""Client of an OpenAI-compatible chat-completions endpoint with a spend cap and one JSON log per call.

The API key is read from ``OPENROUTER_API_KEY``.
"""
import json
import os
import re
import time
from pathlib import Path

import requests

DEFAULT_BASE_URL = 'https://openrouter.ai/api/v1'


class BudgetExceeded(RuntimeError):
    """Raised when the next call could exceed the spend cap."""


class ChatClient:
    """One OpenAI-compatible endpoint with a spend cap and a call log."""

    def __init__(self, log_dir, budget_usd, base_url=DEFAULT_BASE_URL, timeout_s=900):
        self.base_url = base_url.rstrip('/')
        self.api_key = os.environ.get('OPENROUTER_API_KEY', '')
        self.budget_usd = budget_usd
        self.spent_usd = 0.0
        self.calls = 0
        self.timeout_s = timeout_s
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def chat(self, role, model, system, user, max_tokens=16000):
        """Send one system+user exchange; returns the response text ('' on failure)."""
        if not self.api_key:
            raise RuntimeError('OPENROUTER_API_KEY is not set')
        if self.spent_usd >= self.budget_usd:
            raise BudgetExceeded('spent %.4f of %.2f USD' % (self.spent_usd, self.budget_usd))
        body = {'model': model, 'temperature': 0, 'max_tokens': max_tokens, 'usage': {'include': True},
                'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}
        start, text, meta = time.time(), '', {}
        try:
            response = requests.post(self.base_url + '/chat/completions', json=body, timeout=self.timeout_s,
                                     headers={'Authorization': 'Bearer ' + self.api_key})
            payload = response.json()
            text = payload['choices'][0]['message'].get('content') or ''
            usage = payload.get('usage') or {}
            meta = {'model': payload.get('model'), 'usage': usage, 'cost': float(usage.get('cost') or 0)}
        except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
            meta = {'error': str(exc)[:300]}
        self.spent_usd += meta.get('cost', 0.0)
        self.calls += 1
        meta['wall_s'] = round(time.time() - start, 1)
        record = {'role': role, 'model': model, 'system': system, 'user': user, 'response': text, 'meta': meta}
        (self.log_dir / ('%03d_%s.json' % (self.calls, role))).write_text(json.dumps(record, indent=1))
        return text


def parse_json_block(text):
    """First JSON object of a response (inside a ```json fence when present); None if absent."""
    if not text:
        return None
    fenced = re.search(r'```(?:json)?\s*(.*?)```', text, re.S)
    body = fenced.group(1) if fenced else text
    start, end = body.find('{'), body.rfind('}')
    if start < 0 or end < start:
        return None
    try:
        return json.loads(body[start:end + 1])
    except ValueError:
        return None


def parse_files(text, package='tscore_gen'):
    """Engineer output: {relative path: content} from blocks introduced by ``### FILE: <package>/<name>``."""
    files = {}
    pattern = r'###\s*FILE:\s*(\S+)\s*\n```[a-zA-Z]*\n(.*?)```'
    for match in re.finditer(pattern, text or '', re.S):
        path = match.group(1).strip()
        if path.startswith(package + '/') and '..' not in path and path.endswith(('.py', '.md')):
            files[path] = match.group(2)
    return files
