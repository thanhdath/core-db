"""SQLite execution service used by inference and by the training reward.

POST /execute        {dataset_name: bird | spider, db_id, sql, mode: read_only | sandbox_rollback, timeout_ms, max_rows}
                     -> {ok, rows, row_count, error, timed_out}
POST /execute_batch  {dataset_name, db_id, sqls: [...], mode, timeout_ms, max_rows} -> [response, ...]

``bird`` databases are looked up as $BIRD_TRAIN_DB_ROOT/<db_id>/<db_id>.sqlite, then under $BIRD_DEV_DB_ROOT;
``spider`` databases under $SPIDER_DB_ROOT. read_only runs on an immutable connection with case-sensitive LIKE;
sandbox_rollback runs SELECT-like statements on a plain connection and refuses everything else.

Run: uvicorn api:app --app-dir db_execution --host 127.0.0.1 --port 8011 --workers 16
"""
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

SPIDER_DB_ROOT = os.getenv('SPIDER_DB_ROOT', 'data/spider/database')
BIRD_TRAIN_DB_ROOT = os.getenv('BIRD_TRAIN_DB_ROOT', 'data/bird/train/train_databases')
BIRD_DEV_DB_ROOT = os.getenv('BIRD_DEV_DB_ROOT', 'data/bird/dev/dev_databases')
DEFAULT_TIMEOUT_MS = 120000
DEFAULT_MAX_ROWS = 10000
WRITE_PREFIXES = ('INSERT', 'UPDATE', 'DELETE', 'MERGE', 'REPLACE', 'TRUNCATE', 'ALTER', 'DROP', 'CREATE', 'VACUUM',
                  'PRAGMA')
MODE_PATTERN = '^(read_only|sandbox_rollback)$'

app = FastAPI(title='SQLite executor')
gate = threading.Semaphore(int(os.getenv('MAX_CONCURRENT', '100')))


class ExecuteRequest(BaseModel):
    dataset_name: str
    db_id: str
    sql: str
    mode: str = Field('sandbox_rollback', pattern=MODE_PATTERN)
    timeout_ms: int = Field(DEFAULT_TIMEOUT_MS, ge=1, le=120_000)
    max_rows: int = Field(DEFAULT_MAX_ROWS, ge=1, le=1_000_000)


class ExecuteBatchRequest(BaseModel):
    dataset_name: str
    db_id: str
    sqls: List[str]
    mode: str = Field('read_only', pattern=MODE_PATTERN)
    timeout_ms: int = Field(DEFAULT_TIMEOUT_MS, ge=1, le=120_000)
    max_rows: int = Field(DEFAULT_MAX_ROWS, ge=1, le=1_000_000)


class ExecuteResponse(BaseModel):
    ok: bool
    rows: Optional[List[Dict[str, Any]]] = None
    row_count: Optional[int] = None
    error: Optional[str] = None
    timed_out: bool = False


def database_file(dataset_name, db_id):
    """SQLite file <root>/<db_id>/<db_id>.sqlite of a database; 404 if missing."""
    if dataset_name == 'spider':
        roots = [Path(SPIDER_DB_ROOT)]
    elif dataset_name == 'bird':
        roots = [Path(BIRD_TRAIN_DB_ROOT), Path(BIRD_DEV_DB_ROOT)]
    else:
        raise HTTPException(400, detail="dataset_name must be 'bird' or 'spider'")
    if not db_id or '/' in db_id or db_id.startswith('.'):
        raise HTTPException(400, detail='invalid db_id')
    for root in roots:
        path = root / db_id / (db_id + '.sqlite')
        if path.exists():
            return path.absolute()
    raise HTTPException(404, detail='database not found: %s/%s' % (dataset_name, db_id))


def strip_leading_comments(sql):
    """SQL without leading whitespace and leading comments (for statement classification only)."""
    text = sql.lstrip()
    while text.startswith(('--', '/*')):
        end = text.find('\n') if text.startswith('--') else text.find('*/')
        if end == -1:
            return ''
        text = text[end + (1 if text.startswith('--') else 2):].lstrip()
    return text


def is_select_like(sql):
    """True for SELECT / WITH / EXPLAIN statements, ignoring leading comments."""
    return strip_leading_comments(sql).lower().startswith(('select', 'with', 'explain'))


def run_query(connection, sql, max_rows):
    """Rows of one query as dicts (duplicate column names keep the last value)."""
    cursor = connection.execute(sql)
    rows = cursor.fetchall()[:max_rows]
    columns = [d[0] for d in cursor.description] if cursor.description else []
    cursor.close()
    data = [{c: row[i] for i, c in enumerate(columns)} for row in rows] if columns else []
    return ExecuteResponse(ok=True, rows=data, row_count=len(data))


def execute_sql(path, sql, mode, timeout_ms, max_rows):
    """Execute one statement with a wall-clock deadline."""
    deadline = time.time() + timeout_ms / 1000.0
    read_only = mode == 'read_only'
    if not read_only and not is_select_like(sql):
        return ExecuteResponse(ok=False, error='refused: only SELECT/WITH/EXPLAIN statements are executed')
    try:
        target = 'file:%s?immutable=1&mode=ro' % path if read_only else path.as_posix()
        connection = sqlite3.connect(target, uri=read_only, timeout=min(2.0, timeout_ms / 1000.0),
                                     check_same_thread=False)
        try:
            connection.set_progress_handler(lambda: 1 if time.time() >= deadline else 0, 1000)
            if read_only:
                for pragma in ('query_only = ON', 'foreign_keys = ON', 'case_sensitive_like = ON',
                               'busy_timeout=%d' % timeout_ms):
                    connection.execute('PRAGMA %s;' % pragma)
            return run_query(connection, sql, max_rows)
        finally:
            connection.close()
    except sqlite3.OperationalError as exc:
        message = str(exc)
        timed_out = any(word in message for word in ('timeout', 'interrupt', 'exceeded'))
        return ExecuteResponse(ok=False, error=message, timed_out=timed_out)
    except Exception as exc:
        return ExecuteResponse(ok=False, error=str(exc))


def guarded_execute(path, sql, mode, timeout_ms, max_rows):
    """execute_sql under the concurrency gate; writes are rejected in read_only mode."""
    if mode == 'read_only' and sql.strip().upper().startswith(WRITE_PREFIXES):
        raise HTTPException(400, detail="write/DDL statement; use mode='sandbox_rollback'")
    with gate:
        return execute_sql(path, sql, mode, timeout_ms, max_rows)


@app.post('/execute', response_model=ExecuteResponse)
def execute(request: ExecuteRequest):
    path = database_file(request.dataset_name, request.db_id)
    return guarded_execute(path, request.sql, request.mode, request.timeout_ms, request.max_rows)


@app.post('/execute_batch', response_model=List[ExecuteResponse])
def execute_batch(request: ExecuteBatchRequest):
    path = database_file(request.dataset_name, request.db_id)
    return [guarded_execute(path, sql, request.mode, request.timeout_ms, request.max_rows) for sql in request.sqls]


@app.get('/healthz/live')
def live():
    return {'ok': True}
