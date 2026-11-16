"""Agent inputs: schema, column values and statistics of the original database, atomic-operation groups of the
construction pairs (literals abstracted, every group, with example deltas and the distinguishing data pattern) for
the Engineer and the Reviewer, and the Designer's per-column atomic-operation summary (atomic_summary)."""
import json
import re
import sqlite3
from collections import OrderedDict

from ..atomic_operations import OpExtractor
from ..common import quote_identifier as _quote
from ..common import schema_columns
from .atomic_summary import designer_atomic_summary

MAX_EXAMPLES_PER_GROUP = 5
MAX_OP_CHARS = 200
MAX_EXAMPLE_CHARS = 120000
_STRING = re.compile(r"'(?:[^']|'')*'")
_NUMBER = re.compile(r"(?<![A-Za-z_0-9.])-?[0-9]+(?:\.[0-9]+)?(?![A-Za-z_0-9])")
DATA_PATTERNS = (
    (lambda ops: ' LIKE ' in ops, 'values that match the LIKE pattern but differ from the exact literal'),
    (lambda ops: 'COUNT(*)' in ops and re.search(r'COUNT\((?!\*|DISTINCT)', ops),
     'NULL in the nullable column counted by COUNT(column)'),
    (lambda ops: 'DISTINCT' in ops, 'duplicate values after joins and filters'),
    (lambda ops: 'GROUP(' in ops, 'groups with different sizes or aggregate values'),
    (lambda ops: 'ORDER(' in ops or 'LIMIT(' in ops, 'tied sort values and rows with different outputs'),
    (lambda ops: 'JOIN(' in ops or 'TABLE(' in ops, 'matching and unmatched rows allowed by schema constraints'),
    (lambda ops: re.search(r'[<>]', ops), 'values at the comparison boundary (x = c for > vs >=)'),
    (lambda ops: re.search(r'(MAX|MIN|SUM|AVG|COUNT)\(', ops), 'multiple qualifying rows with different values'),
)


def _tables(connection):
    return [r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def schema_text(connection):
    """CREATE statements of every table, index, view and trigger."""
    rows = connection.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")
    return '\n'.join(r[0].strip() + ';' for r in rows)


MAX_VALUE_CHARS = 200


def _shown(value):
    """A sample value as shown to the agents: blobs as '<blob>', long text cut to ``MAX_VALUE_CHARS``."""
    if isinstance(value, bytes):
        return '<blob>'
    if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
        return value[:MAX_VALUE_CHARS] + '...<%d chars>' % len(value)
    return value


def column_values(connection, per_column=8):
    """{table: {column: [up to ``per_column`` distinct non-NULL values]}}."""
    values = {}
    for table in _tables(connection):
        columns = [r[1] for r in connection.execute('PRAGMA table_info(%s)' % _quote(table))]
        values[table] = {}
        for column in columns:
            rows = connection.execute('SELECT DISTINCT %s FROM %s WHERE %s IS NOT NULL LIMIT %d'
                                      % (_quote(column), _quote(table), _quote(column), per_column)).fetchall()
            values[table][column] = [_shown(r[0]) for r in rows]
    return values


STATS_SAMPLE_ROWS = 50000


def _sample_source(connection, table, n_rows):
    """FROM clause of the statistics of one table: the table, or a rowid-stride sample of about STATS_SAMPLE_ROWS
    rows (the first STATS_SAMPLE_ROWS rows of a WITHOUT ROWID table); returns (clause, rows read)."""
    if n_rows <= STATS_SAMPLE_ROWS:
        return _quote(table), n_rows
    stride = -(-n_rows // STATS_SAMPLE_ROWS)
    clause = '(SELECT * FROM %s WHERE rowid %% %d = 0)' % (_quote(table), stride)
    try:
        sampled = connection.execute('SELECT COUNT(*) FROM %s' % clause).fetchone()[0]
    except sqlite3.Error:
        clause = '(SELECT * FROM %s LIMIT %d)' % (_quote(table), STATS_SAMPLE_ROWS)
        sampled = STATS_SAMPLE_ROWS
    return clause, sampled


def column_statistics(connection):
    """{table: {"rows": n, "columns": {column: {"type", "nullable", "null_rate", "distinct"}}}} (observed rows only;
    null_rate and distinct of a table with more than STATS_SAMPLE_ROWS rows come from a rowid-stride sample,
    marked "sampled_rows")."""
    stats = {}
    for table in _tables(connection):
        n_rows = connection.execute('SELECT COUNT(*) FROM %s' % _quote(table)).fetchone()[0]
        source, sampled = _sample_source(connection, table, n_rows)
        columns = {}
        for _cid, column, declared, notnull, _default, pk in connection.execute('PRAGMA table_info(%s)'
                                                                                 % _quote(table)):
            nulls, distinct = connection.execute('SELECT SUM(%s IS NULL), COUNT(DISTINCT %s) FROM %s'
                                                 % (_quote(column), _quote(column), source)).fetchone()
            columns[column] = {'type': declared, 'nullable': 'no' if notnull or pk else 'yes',
                               'null_rate': round((nulls or 0) / sampled, 3) if sampled else None, 'distinct': distinct}
        stats[table] = {'rows': n_rows, 'columns': columns}
        if sampled != n_rows:
            stats[table]['sampled_rows'] = sampled
    return stats


def pair_delta(extractor, gold, neighbor):
    """(gold ops, added ops, removed ops) as sorted lists; None when either query cannot be parsed."""
    try:
        gold_ops, neighbor_ops = set(extractor.keys(gold)), set(extractor.keys(neighbor))
    except Exception:
        return None
    return sorted(gold_ops), sorted(neighbor_ops - gold_ops), sorted(gold_ops - neighbor_ops)


def abstract_op(op):
    """An atomic operation with its literals abstracted (strings -> <str>, numbers -> <num>)."""
    return _NUMBER.sub('<num>', _STRING.sub('<str>', op))


def group_key(delta):
    """Key of the literal-abstracted delta (added, removed operations) of one pair."""
    return json.dumps([sorted({abstract_op(o) for o in delta[1]}), sorted({abstract_op(o) for o in delta[2]})])


def data_patterns(key):
    """Distinguishing data patterns of one group key (the <str> / <num> placeholders are removed before the tests, so
    that their '<' and '>' do not read as comparisons)."""
    ops = ' '.join(sum(json.loads(key), [])).upper().replace('<STR>', 'STR').replace('<NUM>', 'NUM')
    return [pattern for test, pattern in DATA_PATTERNS if test(ops)] or ['values of the changed columns that differ']


def group_pairs(extractor, pairs):
    """Groups of the pairs by literal-abstracted delta; returns (groups, statistics)."""
    groups, stats = OrderedDict(), {'pairs': len(pairs), 'parse_errors': 0, 'empty_delta': 0}
    for pair in pairs:
        delta = pair_delta(extractor, pair['gold_sql'], pair['neighbor_sql'])
        if delta is None:
            stats['parse_errors'] += 1
            continue
        if not delta[1] and not delta[2]:
            stats['empty_delta'] += 1
            continue
        key = group_key(delta)
        added, removed = ([o[:MAX_OP_CHARS] for o in ops] for ops in json.loads(key))
        group = groups.setdefault(key, {'added_ops': added, 'removed_ops': removed, 'pair_count': 0, 'sources': [],
                                        'examples': [], 'data_pattern': data_patterns(key)})
        group['pair_count'] += 1
        if pair.get('source') not in group['sources']:
            group['sources'].append(pair.get('source'))
        example = {'added': [o[:MAX_OP_CHARS] for o in delta[1]], 'removed': [o[:MAX_OP_CHARS] for o in delta[2]]}
        if len(group['examples']) < MAX_EXAMPLES_PER_GROUP and example not in group['examples']:
            group['examples'].append(example)
    stats['groups'] = len(groups)
    return list(groups.values()), stats


def atomic_operation_text(compact, pairs):
    """Every atomic-operation group of the construction pairs (largest groups first); literal examples are kept for
    the largest groups while the examples stay under MAX_EXAMPLE_CHARS."""
    groups, stats = group_pairs(OpExtractor(schema_columns(compact)), pairs)
    groups.sort(key=lambda g: -g['pair_count'])
    budget = MAX_EXAMPLE_CHARS
    for group in groups:
        size = len(json.dumps(group['examples']))
        if size > budget:
            group['examples'] = []
        budget -= len(json.dumps(group['examples']))
    stats['groups_with_examples'] = sum(bool(g['examples']) for g in groups)
    return json.dumps({'groups': groups, 'stats': stats})


def agent_inputs(original, compact, pairs):
    """Prompt-ready inputs of the three agents: schema, column values and statistics of the original database; the
    Engineer and the Reviewer get the full atomic-operation groups, the Designer the per-column summary with its
    generation targets (atomic_summary)."""
    connection = sqlite3.connect('file:%s?mode=ro' % original, uri=True)
    connection.text_factory = lambda b: b.decode('utf-8', errors='replace')
    try:
        return {'schema': schema_text(connection),
                'column_values': json.dumps(column_values(connection), default=str),
                'column_statistics': json.dumps(column_statistics(connection)),
                'atomic_operations': atomic_operation_text(compact, pairs),
                'atomic_operations_designer': designer_atomic_summary(compact, pairs, original=original)}
    finally:
        connection.close()
