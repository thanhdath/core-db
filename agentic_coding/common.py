"""SQL execution, result comparison and JSON helpers shared by every CoRE-DB build step.

Two results are equal when their row multisets are equal, or their row
sequences when the gold query has a top-level ORDER BY.  A result is *informative* when it has at least one
row with a non-NULL value.  Execution errors and timeouts are ``unknown`` and never count as a separation.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import os
import re
import sqlite3
import time

QUERY_TIMEOUT_S = float(os.environ.get('COREDB_QUERY_TIMEOUT_S', '2.0'))
MAX_ROWS = 10000
_ORDER_BY = re.compile(r'order\s+by', re.I)


def sha_text(text):
    """SHA-256 hex digest of a string."""
    return hashlib.sha256(text.encode()).hexdigest()


def sha_file(path):
    """SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def save_json(path, data):
    """Write JSON atomically (temporary file + rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=1, default=str))
    tmp.replace(path)


def load_json(path):
    """Read a JSON file."""
    return json.loads(Path(path).read_text())


def read_jsonl(path):
    """Read a JSON-lines file into a list of dicts."""
    with open(path) as handle:
        return [json.loads(line) for line in handle if line.strip()]


def quote_identifier(name):
    """Double-quote an SQLite identifier."""
    return '"%s"' % name.replace('"', '""')


def schema_columns(path):
    """{table: [column, ...]} of a SQLite database."""
    connection = connect(path)
    try:
        tables = [r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {t: [r[1] for r in connection.execute('PRAGMA table_info(%s)' % quote_identifier(t))] for t in tables}
    finally:
        connection.close()


def has_top_level_order(sql):
    """True when the query has an ORDER BY outside every parenthesis."""
    depth, text = 0, sql or ''
    for i, char in enumerate(text):
        depth += char == '('
        depth -= char == ')'
        if depth == 0 and _ORDER_BY.match(text, i):
            return True
    return False


def _canonical(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, bytes):
        return 'b:' + value.hex()
    return value


def connect(path):
    """Open a SQLite file read-only (immutable) with case-sensitive LIKE."""
    connection = sqlite3.connect('file:%s?mode=ro&immutable=1' % path, uri=True)
    connection.execute('PRAGMA case_sensitive_like=ON')
    return connection


def execute(connection, sql):
    """Run one query and return a compact record: ok, row count, informative flag and result hashes."""
    start = time.monotonic()
    connection.set_progress_handler(lambda: int(time.monotonic() - start > QUERY_TIMEOUT_S), 1000)
    try:
        rows = connection.execute(sql).fetchmany(MAX_ROWS + 1)
    except Exception as exc:
        return {'ok': False, 'error': str(exc)[:80]}
    finally:
        connection.set_progress_handler(None, 0)
    if len(rows) > MAX_ROWS:
        return {'ok': False, 'error': 'row_cap'}
    tuples = [tuple(_canonical(v) for v in row) for row in rows]
    informative = bool(tuples) and not all(v is None for row in tuples for v in row)
    bag = sorted(Counter(map(repr, tuples)).items())
    return {'ok': True, 'n': len(tuples), 'informative': informative,
            'seq': sha_text(repr(tuples)), 'bag': sha_text(repr(bag))}


def execute_all(path, sqls):
    """Execute every SQL once on one database; returns {sha_text(sql): record}."""
    connection = connect(path)
    try:
        return {sha_text(sql): execute(connection, sql) for sql in sqls}
    finally:
        connection.close()


def pair_status(gold_result, candidate_result, ordered):
    """Status of one (gold, candidate) pair on one database: unknown, uninformative, accept or refuse."""
    if gold_result is None or candidate_result is None:
        return 'unknown'
    if not gold_result['ok'] or not candidate_result['ok']:
        return 'unknown'
    if not gold_result['informative']:
        return 'uninformative'
    key = 'seq' if ordered else 'bag'
    return 'accept' if gold_result[key] == candidate_result[key] else 'refuse'


def coredb_verdict(statuses):
    """CoRE-DB aggregation over members: any refusal refuses, else any unknown is unknown, else accept."""
    statuses = [s for s in statuses if s != 'uninformative']
    if not statuses:
        return 'unknown'
    if 'refuse' in statuses:
        return 'refuse'
    if 'unknown' in statuses:
        return 'unknown'
    return 'accept'


def worker_count(default=4):
    """Number of worker processes (env COREDB_WORKERS)."""
    return int(os.environ.get('COREDB_WORKERS', default))
