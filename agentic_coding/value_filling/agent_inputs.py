"""Agent inputs: schema, column values and statistics of the compact database, and atomic-operation deltas."""
import json
import sqlite3
from collections import OrderedDict

from ..atomic_operations import OpExtractor
from ..common import quote_identifier as _quote
from ..common import schema_columns

MAX_GROUPS_IN_PROMPT = 120


def _tables(connection):
    return [r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def schema_text(connection):
    """CREATE statements of every table, index, view and trigger."""
    rows = connection.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")
    return '\n'.join(r[0].strip() + ';' for r in rows)


def column_values(connection, per_column=8):
    """{table: {column: [up to ``per_column`` distinct non-NULL values]}}."""
    values = {}
    for table in _tables(connection):
        columns = [r[1] for r in connection.execute('PRAGMA table_info(%s)' % _quote(table))]
        values[table] = {}
        for column in columns:
            rows = connection.execute('SELECT DISTINCT %s FROM %s WHERE %s IS NOT NULL LIMIT %d'
                                      % (_quote(column), _quote(table), _quote(column), per_column)).fetchall()
            values[table][column] = [r[0] if not isinstance(r[0], bytes) else '<blob>' for r in rows]
    return values


def column_statistics(connection):
    """{table: {"rows": n, "columns": {column: {"type", "null_rate", "distinct"}}}}."""
    stats = {}
    for table in _tables(connection):
        n_rows = connection.execute('SELECT COUNT(*) FROM %s' % _quote(table)).fetchone()[0]
        columns = {}
        for _cid, column, declared, _nn, _default, _pk in connection.execute('PRAGMA table_info(%s)' % _quote(table)):
            nulls, distinct = connection.execute('SELECT SUM(%s IS NULL), COUNT(DISTINCT %s) FROM %s'
                                                 % (_quote(column), _quote(column), _quote(table))).fetchone()
            columns[column] = {'type': declared, 'null_rate': round((nulls or 0) / n_rows, 3) if n_rows else None,
                               'distinct': distinct}
        stats[table] = {'rows': n_rows, 'columns': columns}
    return stats


def pair_delta(extractor, gold, neighbor):
    """(gold ops, added ops, removed ops) as sorted lists; None when either query cannot be parsed."""
    try:
        gold_ops, neighbor_ops = set(extractor.keys(gold)), set(extractor.keys(neighbor))
    except Exception:
        return None
    return sorted(gold_ops), sorted(neighbor_ops - gold_ops), sorted(gold_ops - neighbor_ops)


def group_pairs(extractor, pairs):
    """Merge identical deltas of the pairs; returns (groups, statistics)."""
    groups, stats = OrderedDict(), {'pairs': len(pairs), 'parse_errors': 0, 'empty_delta': 0}
    for pair in pairs:
        delta = pair_delta(extractor, pair['gold_sql'], pair['neighbor_sql'])
        if delta is None:
            stats['parse_errors'] += 1
            continue
        if not delta[1] and not delta[2]:
            stats['empty_delta'] += 1
            continue
        group = groups.setdefault(json.dumps(delta), {'gold_ops': delta[0], 'added_ops': delta[1],
                                                      'removed_ops': delta[2], 'pair_count': 0, 'sources': []})
        group['pair_count'] += 1
        if pair.get('source') not in group['sources']:
            group['sources'].append(pair.get('source'))
    return list(groups.values()), stats


def atomic_operation_text(compact, pairs):
    """Atomic-operation deltas of the construction pairs (largest groups first)."""
    groups, stats = group_pairs(OpExtractor(schema_columns(compact)), pairs)
    groups.sort(key=lambda g: -g['pair_count'])
    return json.dumps({'groups': groups[:MAX_GROUPS_IN_PROMPT], 'stats': stats})


def agent_inputs(compact, pairs):
    """Prompt-ready inputs of the three agents."""
    connection = sqlite3.connect('file:%s?mode=ro' % compact, uri=True)
    connection.text_factory = lambda b: b.decode('utf-8', errors='replace')
    try:
        return {'schema': schema_text(connection),
                'column_values': json.dumps(column_values(connection), default=str),
                'column_statistics': json.dumps(column_statistics(connection)),
                'atomic_operations': atomic_operation_text(compact, pairs)}
    finally:
        connection.close()
