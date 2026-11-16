"""Client of an OpenAI-compatible chat-completions endpoint with a spend cap and one JSON log per call."""
import json
import os
import re
import threading
import time
from pathlib import Path

import requests

DEFAULT_BASE_URL = 'https://openrouter.ai/api/v1'


class BudgetExceeded(RuntimeError):
    """Raised when the next call could exceed the spend cap."""


class ChatClient:
    """One OpenAI-compatible endpoint with a spend cap and a call log."""

    def __init__(self, log_dir, budget_usd, base_url=DEFAULT_BASE_URL, timeout_s=240):
        self.base_url = base_url.rstrip('/')
        self.api_key = os.environ.get('OPENROUTER_API_KEY', '')
        self.budget_usd = budget_usd
        self.spent_usd = 0.0
        self.calls = 0
        self.last_cost = 0.0
        self.last_finish_reason = None
        self.timeout_s = timeout_s
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def max_completion_tokens(self, model):
        """Largest completion of the model from the models endpoint (top_provider); None if unknown."""
        try:
            data = requests.get(self.base_url + '/models', timeout=60).json()['data']
            return next(int(m['top_provider']['max_completion_tokens']) for m in data if m['id'] == model)
        except (requests.RequestException, KeyError, TypeError, ValueError, StopIteration):
            return None

    def _post(self, body):
        """POST one request in a daemon thread; TimeoutError after ``timeout_s`` seconds of wall time."""
        result = {}

        def target():
            try:
                response = requests.post(self.base_url + '/chat/completions', json=body, timeout=self.timeout_s + 60,
                                         headers={'Authorization': 'Bearer ' + self.api_key})
                result['payload'] = response.json()
            except Exception as exc:
                result['error'] = exc

        worker = threading.Thread(target=target, daemon=True)
        worker.start()
        worker.join(self.timeout_s)
        if worker.is_alive():
            raise TimeoutError('per-call wall limit of %d s' % self.timeout_s)
        if 'error' in result:
            raise result['error']
        return result['payload']

    def chat(self, role, model, system, user, max_tokens=16000, reserve=0.0):
        """Send one system+user exchange with reasoning off; returns the response text ('' on failure)."""
        if not self.api_key:
            raise RuntimeError('OPENROUTER_API_KEY is not set')
        if self.spent_usd + reserve >= self.budget_usd:
            raise BudgetExceeded('spent %.4f + reserve %.4f of %.2f USD' % (self.spent_usd, reserve, self.budget_usd))
        body = {'model': model, 'temperature': 0, 'max_tokens': max_tokens, 'usage': {'include': True},
                'reasoning': {'enabled': False},
                'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}
        start, text, meta = time.time(), '', {}
        try:
            try:
                payload = self._post(body)
            except (TimeoutError, requests.RequestException, ValueError):
                payload = self._post(body)
            text = payload['choices'][0]['message'].get('content') or ''
            usage = payload.get('usage') or {}
            meta = {'model': payload.get('model'), 'usage': usage, 'cost': float(usage.get('cost') or 0),
                    'finish_reason': payload['choices'][0].get('finish_reason'), 'max_tokens': max_tokens}
        except (TimeoutError, requests.RequestException, KeyError, IndexError, ValueError) as exc:
            meta = {'error': str(exc)[:300]}
        self.last_cost, self.last_finish_reason = meta.get('cost', 0.0), meta.get('finish_reason')
        self.spent_usd += self.last_cost
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
    """Engineer output: {relative path: content} from blocks introduced by ``### FILE: <package>/<name>``, the header
    line written before the code fence or as the first line inside it."""
    files = {}
    pattern = r'###\s*FILE:\s*(\S+)\s*\n```[a-zA-Z]*\n(.*?)```|```[a-zA-Z]*\n###\s*FILE:\s*(\S+)\s*\n(.*?)```'
    for match in re.finditer(pattern, text or '', re.S):
        path, content = match.group(1, 2) if match.group(1) else match.group(3, 4)
        path = path.strip()
        if path.startswith(package + '/') and '..' not in path and path.endswith(('.py', '.md')):
            files[path] = content
    return files
