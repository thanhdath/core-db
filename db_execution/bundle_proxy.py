"""CoRE-DB proxy: executes a query on every member (compact database + selected instances) of a database.

For a db_id listed in $COREDB_TREE/members.json ({db_id: [db_id, instance, ...]}) the request is sent to the
execution API ($COREDB_UPSTREAM) once per member. The reply carries the first member's ok/error/timed_out and
    rows   = [{"__member__": i, **row}, ...] for every member i, or {"__member__": i, "__error__": message}
             for a member i > 0 whose execution failed,
    bundle = {"members": [...], "member_truncated": [...]}.
Comparing row sets of these tagged rows therefore compares gold and prediction on every member at once.
Other databases are passed through unchanged.

Run: COREDB_TREE=coredb_tree uvicorn bundle_proxy:app --app-dir db_execution --host 127.0.0.1 --port 8021
"""
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

UPSTREAM = os.getenv('COREDB_UPSTREAM', 'http://127.0.0.1:8011').rstrip('/')
TREE = Path(os.environ['COREDB_TREE'])
MEMBERS = json.loads((TREE / 'members.json').read_text())
DATASET_OF = {db: ds for db in MEMBERS for ds in ('bird', 'spider') if (TREE / ds / db / (db + '.sqlite')).exists()}
POOL = ThreadPoolExecutor(max_workers=64)
LOCAL = threading.local()

app = FastAPI(title='CoRE-DB proxy')


def session():
    """One requests session per thread, ignoring proxy environment variables."""
    if not hasattr(LOCAL, 'session'):
        LOCAL.session = requests.Session()
        LOCAL.session.trust_env = False
    return LOCAL.session


def post(payload, timeout):
    """(status, json or None, text, exception message or None) of one upstream call."""
    try:
        response = session().post(UPSTREAM + '/execute', json=payload, timeout=timeout)
    except Exception as exc:
        return None, None, '', '%s: %s' % (type(exc).__name__, exc)
    try:
        data = response.json()
    except ValueError:
        data = None
    return response.status_code, data, response.text, None


def failure(message):
    return JSONResponse({'ok': False, 'rows': None, 'row_count': None, 'error': message, 'timed_out': False})


def relay(status, data, text):
    """Upstream reply returned as is."""
    if data is None:
        return JSONResponse(status_code=status or 502, content={'detail': text[:2000]})
    return JSONResponse(status_code=status, content=data)


def member_error(status, data, text, exc):
    """Error message of one member call, or None when it succeeded."""
    if exc is not None:
        return exc
    if status != 200:
        return 'HTTP %s: %s' % (status, text[:500])
    if not isinstance(data, dict):
        return 'malformed upstream reply'
    if data.get('ok') is not True:
        return str(data.get('error') or ('timed out' if data.get('timed_out') else 'not ok'))
    if data.get('rows') is not None and not isinstance(data.get('rows'), list):
        return 'malformed rows'
    return None


def tagged_rows(results, max_rows):
    """Member-tagged rows and per-member truncation flags."""
    rows, truncated = [], []
    for i, result in enumerate(results):
        error = member_error(*result)
        if error is None:
            member_rows = result[1].get('rows') or []
            rows.extend({'__member__': i, **row} for row in member_rows)
            truncated.append(len(member_rows) >= max_rows)
        else:
            rows.append({'__member__': i, '__error__': error})
            truncated.append(False)
    return rows, truncated


@app.post('/execute')
def execute(body: dict = Body(...)):
    db_id = body.get('db_id')
    if not isinstance(db_id, str) or not db_id:
        return failure('bad request: db_id required')
    timeout = max(1.0, int(body.get('timeout_ms', 120000)) / 1000.0) + 5.0
    members = MEMBERS.get(db_id)
    if not members or DATASET_OF.get(db_id) != body.get('dataset_name'):
        status, data, text, exc = post(body, timeout)
        return failure('proxy upstream error: %s' % exc) if exc else relay(status, data, text)
    results = list(POOL.map(lambda member: post(dict(body, db_id=member), timeout), members))
    status, first, text, exc = results[0]
    if exc is not None:
        return failure('proxy upstream error: %s' % exc)
    if status != 200 or not isinstance(first, dict):
        return relay(status, first, text)
    reply = dict(first)
    truncated = [False] * len(members)
    if first.get('ok') is True:
        reply['rows'], truncated = tagged_rows(results, int(body.get('max_rows', 10000)))
        reply['row_count'] = len(reply['rows'])
    reply['bundle'] = {'members': members, 'member_truncated': truncated}
    return JSONResponse(reply)


@app.get('/healthz/live')
def live():
    return {'ok': True}
