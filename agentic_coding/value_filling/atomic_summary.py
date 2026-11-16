"""Designer input: the atomic operations of the construction pairs as one entry per table.column."""
import json
import math
import re
import sqlite3
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache

import sqlglot
from sqlglot import exp

from ..atomic_operations import OpExtractor
from ..common import quote_identifier as _quote
from ..common import schema_columns

BOUNDARY = 'comparison_boundary'
LIKE = 'like_near_variant'
AGGREGATE_BOUNDARY = 'aggregate_boundary'
NULL_IN_COUNT = 'null_in_count_column'
NULL_ROWS = 'null_rows'
DUPLICATES = 'duplicates_for_distinct'
TIES = 'ties_for_order_limit'
UNMATCHED = 'unmatched_join_rows'
GROUP_SIZES = 'group_sizes'
DIFFERENT_VALUES = 'rows_with_different_values'
PATTERN_ORDER = (BOUNDARY, LIKE, AGGREGATE_BOUNDARY, NULL_IN_COUNT, NULL_ROWS, DUPLICATES, TIES, UNMATCHED,
                 GROUP_SIZES, DIFFERENT_VALUES)
VALUE_PATTERNS = (BOUNDARY, LIKE, AGGREGATE_BOUNDARY, NULL_ROWS)
COUNT_TERM = 'count_term'

CHARS_PER_PAIR, MIN_CHARS, MAX_CHARS = 38, 8000, 30000
MAX_POOL_LITERALS = 5
SIZE_LEVEL_KEYS = ('columns', 'value_ops', 'other_ops', 'op_chars', 'values', 'min_pairs', 'examples', 'example_ops',
                   'pool_columns', 'details')
SIZE_LEVELS = tuple(dict(zip(SIZE_LEVEL_KEYS, caps)) for caps in (
    (40, 6, 2, 160, 12, 1, 2, 3, 25, 2),
    (40, 4, 1, 140, 12, 2, 2, 3, 20, 2),
    (40, 3, 1, 120, 10, 2, 1, 2, 15, 1),
    (40, 2, 1, 100, 8, 3, 1, 2, 10, 1),
    (40, 2, 0, 100, 8, 3, 1, 2, 10, 1),
    (40, 2, 0, 90, 8, 4, 1, 2, 5, 1),
    (40, 2, 0, 90, 6, 5, 1, 1, 0, 1),
    (40, 1, 0, 80, 6, 6, 1, 1, 0, 1),
    (35, 1, 0, 80, 6, 6, 1, 1, 0, 1),
    (30, 1, 0, 80, 6, 6, 1, 1, 0, 1),
    (25, 1, 0, 80, 6, 6, 1, 1, 0, 1),
    (20, 1, 0, 70, 6, 6, 1, 1, 0, 1),
    (15, 1, 0, 70, 6, 6, 0, 1, 0, 1)))
VALUE_MIN_PAIRS = 2
NULL_SHARE = '5-30 % of generated rows'
NO_NULL = 'none (NOT NULL column)'
DUPLICATE_SHARE = '20-50 %'
GROUP_SIZE_TARGET = '1, 2 and >= 3'
DIFFERENT_VALUES_TARGET = '>= 2 per group with different values'
NO_LIMIT = 'any (no LIMIT)'
UNORDERED = 'unordered'
UNRESOLVED_TABLE = 'unresolved__'
ONE_DAY = timedelta(days=1)

_COMPARISONS = {exp.EQ: '=', exp.NEQ: '<>', exp.GT: '>', exp.GTE: '>=', exp.LT: '<', exp.LTE: '<='}
_MIRRORED = {'=': '=', '<>': '<>', '>': '<', '>=': '<=', '<': '>', '<=': '>='}
_TRANSPARENT_NAMES = ('Paren', 'Alias', 'Cast', 'TryCast', 'Lower', 'Upper', 'Trim', 'TsOrDsToTimestamp',
                      'TsOrDsToDate')
_TRANSPARENT = tuple(getattr(exp, name) for name in _TRANSPARENT_NAMES if hasattr(exp, name))
_PREDICATES = tuple(_COMPARISONS) + (exp.Like, exp.ILike, exp.In, exp.Between, exp.Is, exp.And, exp.Or, exp.Not)
_SPREAD_AGGREGATES = (exp.Max, exp.Min, exp.Sum, exp.Avg)
_AGGREGATES = _SPREAD_AGGREGATES + (exp.Count,)
_OPERATION = re.compile(r'^((?:[a-z_]+:)*)([A-Z_]+)(?:\((.*)\))?$', re.S)
_ALIAS_OR_STRING = re.compile(r"'(?:[^']|'')*'|(?P<alias>#\d+(?=\.)|\b(?:derived|cte):|\?(?=\.))")
_DATE_LITERAL = re.compile(r'^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?(?:[ T][0-9:.]*)?$')
_DATE_PARTS = ('%Y', '%Y-%m', '%Y-%m-%d')
_SUBSTRING_PARTS = {4: '%Y', 7: '%Y-%m', 10: '%Y-%m-%d'}
_ISO_DATE = re.compile(r'^\d{4}-\d{2}')
_DATE_PREFIX = re.compile(r'^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?%$')
_DATE_SHAPES = (
    (re.compile(r'\d{4}-\d{2}-\d{2}$'), '%Y-%m-%d'),
    (re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$'), '%Y-%m-%d %H:%M:%S'),
    (re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.(\d+)$'), '%Y-%m-%d %H:%M:%S.'),
    (re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$'), '%Y-%m-%dT%H:%M:%S'),
    (re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}$'), '%Y-%m-%d %H:%M'),
    (re.compile(r'\d{4}/\d{2}/\d{2}$'), '%Y/%m/%d'),
    (re.compile(r'\d{1,2}/\d{1,2}/\d{4}$'), '%m/%d/%Y'),
    (re.compile(r'\d{4}-\d{2}$'), '%Y-%m'),
)


@dataclass(frozen=True)
class ColumnInfo:
    """Schema facts of one column, names as declared."""
    table: str
    column: str
    declared_type: str
    nullable: bool

    @property
    def name(self):
        return '%s.%s' % (self.table, self.column)


def table_names(connection):
    return [r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def decimal_places(value):
    """Decimal places of a number (at most 6)."""
    if not isinstance(value, float) or value.is_integer():
        return 0
    return len(('%.6f' % value).rstrip('0').split('.')[1])


def date_shape(text):
    """(strftime format, fraction digits or None) of one date/time text, or None."""
    for shape, date_format in _DATE_SHAPES:
        match = shape.match(text)
        if match:
            return date_format, (match.group(1) if date_format.endswith('.') else None)
    return None


def detect_date_format(values):
    """strftime format shared by >= 80 % of the sampled non-NULL values of a column, None when they are no date/time
    texts; a fraction that every value carries (works_cycles '.0') is kept literally, a varying one is %f."""
    shapes = [date_shape(v.strip()) if isinstance(v, str) else None for v in values]
    formats = Counter(shape[0] for shape in shapes if shape)
    if not formats:
        return None
    date_format, count = formats.most_common(1)[0]
    if count < 0.8 * len(shapes):
        return None
    if date_format.endswith('.'):
        fractions = {shape[1] for shape in shapes if shape and shape[0] == date_format}
        return date_format + (fractions.pop() if len(fractions) == 1 else '%f')
    if date_format == '%m/%d/%Y' and any(int(v.split('/')[0]) > 12 for v, shape in zip(values, shapes) if shape):
        return '%d/%m/%Y'
    return date_format


class ColumnCatalog:
    """Columns, foreign keys, date formats and numeric steps of the database whose values describe the columns."""

    def __init__(self, connection):
        self.connection = connection
        self.columns, self.foreign_keys, self.by_column_name = {}, {}, defaultdict(list)
        self._date_formats, self._steps = {}, {}
        for table in table_names(connection):
            self._add_table(table)

    def _add_table(self, table):
        for _cid, column, declared, notnull, _default, pk in self.connection.execute(
                'PRAGMA table_info(%s)' % _quote(table)):
            info = ColumnInfo(table, column, declared or '', not (notnull or pk))
            self.columns[(table.lower(), column.lower())] = info
            self.by_column_name[column.lower()].append(info)
        for row in self.connection.execute('PRAGMA foreign_key_list(%s)' % _quote(table)):
            parent, child_column, parent_column = row[2], row[3], row[4]
            self.foreign_keys[(table.lower(), child_column.lower())] = (parent.lower(),
                                                                        (parent_column or child_column).lower())

    def resolve(self, ref):
        """ColumnInfo of a lower-case (table, column) reference; an unqualified column resolves when its name is
        unique in the schema; None for derived tables, CTEs and unknown names."""
        if ref is None:
            return None
        table, column = ref
        if table in (UNRESOLVED_TABLE, '?'):
            matches = self.by_column_name.get(column, [])
            return matches[0] if len(matches) == 1 else None
        return self.columns.get((table, column))

    def child_column(self, info, partner):
        """The foreign-key (child) column of a join edge; ``info`` itself when no key relates the two columns."""
        key = (info.table.lower(), info.column.lower())
        partner_key = (partner.table.lower(), partner.column.lower())
        return partner if self.foreign_keys.get(partner_key) == key else info

    def date_format(self, info):
        """strftime format of a date/time text column (detected from its values), else None."""
        if info.name not in self._date_formats:
            values = [r[0] for r in self.connection.execute(
                'SELECT substr(%s, 1, 40) FROM %s WHERE %s IS NOT NULL LIMIT 200'
                % (_quote(info.column), _quote(info.table), _quote(info.column)))]
            self._date_formats[info.name] = detect_date_format(values)
        return self._date_formats[info.name]

    def numeric_step(self, info):
        """Observed step of a numeric column (1 for whole numbers, 10^-d for d decimals, d <= 4), None without
        numeric values."""
        if info.name not in self._steps:
            places = [decimal_places(r[0]) for r in self.connection.execute(
                "SELECT DISTINCT %s FROM %s WHERE typeof(%s) IN ('integer', 'real') LIMIT 200"
                % (_quote(info.column), _quote(info.table), _quote(info.column)))]
            digits = min(max(places), 4) if places else None
            self._steps[info.name] = None if digits is None else 1 if digits == 0 else 10 ** -digits
        return self._steps[info.name]


def split_op(op):
    """(sub-query prefix, kind, argument) of an operation key, e.g. ('scalar:', 'PRED', "games.season = 'Winter'")."""
    match = _OPERATION.match(op)
    return (match.group(1), match.group(2), match.group(3) or '') if match else ('', '', op)


def op_kind(op):
    return split_op(op)[1]


def _plain_alias(match):
    alias = match.group('alias')
    if alias is None:
        return match.group(0)
    if alias.startswith('#'):
        return ''
    return UNRESOLVED_TABLE if alias == '?' else alias[:-1] + '__'


@lru_cache(maxsize=50000)
def parse_argument(text):
    """sqlglot tree of an operation argument ('t#2.c' read as 't.c', 'derived:d.c' as 'derived__d.c', '?.c' as an
    unresolved table); None when it does not parse."""
    try:
        return sqlglot.parse_one(_ALIAS_OR_STRING.sub(_plain_alias, text), read='sqlite')
    except Exception:
        return None


def table_name(text):
    """Lower-case table name of a canonical table ('person#2' -> 'person')."""
    return re.sub(r'#\d+$', '', text.strip().lower())


def split_ref(text):
    """(table, column) of a canonical column reference 'table.column'."""
    table, _, column = text.strip().rpartition('.')
    return table_name(table), column.lower()


def join_refs(argument):
    """The two column references of a JOIN argument 'a.c=b.d'."""
    left, _, right = argument.partition('=')
    return split_ref(left), split_ref(right)


def order_parts(argument):
    """(expression text, 'ASC' | 'DESC') of an ORDER argument 'expr, DESC'."""
    text, _, direction = argument.rpartition(', ')
    return (text, direction) if direction in ('ASC', 'DESC') else (argument, 'ASC')


def to_number(text):
    """int or finite float of a numeric text, else None."""
    try:
        return int(text)
    except (TypeError, ValueError):
        try:
            value = float(text)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None


def limit_rank(kind, argument):
    """Tie rank of LIMIT k (k) or OFFSET n (n + 1); None for a missing or negative bound."""
    number = to_number(argument)
    if not isinstance(number, int) or number < 0 or (kind == 'LIMIT' and number == 0):
        return None
    return number + 1 if kind == 'OFFSET' else number


def child_nodes(node):
    for value in node.args.values():
        for child in value if isinstance(value, list) else (value,):
            if isinstance(child, exp.Expression):
                yield child


def nodes_outside_subqueries(node):
    """``node`` and its descendants in document order, without entering sub-queries (separate operation keys)."""
    if isinstance(node, (exp.Select, exp.Subquery)):
        return
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed([c for c in child_nodes(current) if not isinstance(c, (exp.Select, exp.Subquery))]))


def column_ref(column):
    """Lower-case (table, column) of a qualified column node."""
    return column.table.lower(), column.name.lower()


def column_refs(node):
    """References of the qualified columns of an expression outside its sub-queries, in order, without repeats."""
    refs = []
    for current in nodes_outside_subqueries(node):
        if isinstance(current, exp.Column) and current.table and column_ref(current) not in refs:
            refs.append(column_ref(current))
    return refs


def literal_value(node):
    """Value of a string, number or negated number literal under parentheses; None for any other node."""
    while isinstance(node, exp.Paren):
        node = node.this
    if isinstance(node, exp.Neg):
        value = literal_value(node.this)
        return -value if isinstance(value, (int, float)) else None
    if isinstance(node, exp.Literal):
        return node.this if node.is_string else to_number(node.this)
    return None


def unwrap(node):
    """The operand under value-preserving wrappers (parentheses, aliases, CAST, LOWER / UPPER / TRIM)."""
    while isinstance(node, _TRANSPARENT) and isinstance(node.this, exp.Expression):
        node = node.this
    return node


def aggregate_of(node):
    """The aggregate function at the top of ``node`` (under wrappers), else None."""
    node = unwrap(node)
    return node if isinstance(node, _AGGREGATES) else None


def subquery_select(node):
    """The SELECT of a sub-query node, else None."""
    while isinstance(node, (exp.Subquery, exp.Paren)):
        node = node.this
    return node if isinstance(node, exp.Select) else None


def date_part(side):
    """(column node, '%Y' | '%Y-%m' | '%Y-%m-%d') of a date-part extraction such as STRFTIME('%Y', col) or
    SUBSTR(col, 1, 4); None otherwise."""
    node = unwrap(side)
    if isinstance(node, exp.TimeToStr):
        part, column = literal_value(node.args.get('format')), unwrap(node.this)
        if part in _DATE_PARTS and isinstance(column, exp.Column) and column.table:
            return column, part
    if isinstance(node, exp.Substring):
        column = unwrap(node.this)
        start, length = literal_value(node.args.get('start')), literal_value(node.args.get('length'))
        if isinstance(column, exp.Column) and column.table and start == 1 and length in _SUBSTRING_PARTS:
            return column, _SUBSTRING_PARTS[length]
    return None


def parse_date(value):
    """date of a 'YYYY-M[M][-D[D]][ time]' literal (a month alone is its first day); None otherwise."""
    match = _DATE_LITERAL.match(value) if isinstance(value, str) else None
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3) or 1))
    except ValueError:
        return None


def shorten(text, limit):
    return text if len(text) <= limit else text[:limit - 3] + '...'


def comparison_target(side, operator, value):
    """(column refs, target) of ``side`` compared with a literal: a year or a date of a date-part extraction, a
    number / string / date of a column, else the expression of its columns; None without a column."""
    part = date_part(side)
    if part is not None:
        column, fmt = part
        if fmt == '%Y' and isinstance(value, int):
            return [column_ref(column)], ('year', operator, value)
        day = parse_date(value)
        if day is not None:
            return [column_ref(column)], ('date', operator, day.isoformat())
    operand = unwrap(side)
    if isinstance(operand, exp.Column) and operand.table:
        day = parse_date(value)
        if day is not None:
            return [column_ref(operand)], ('date', operator, day.isoformat())
        return [column_ref(operand)], ('string' if isinstance(value, str) else 'number', operator, value)
    refs = column_refs(side)
    if not refs or not isinstance(value, (int, float)) or isinstance(unwrap(side), _PREDICATES):
        return None
    while isinstance(side, exp.Paren):
        side = side.this
    return refs[:3], ('expression', operator, value, shorten(side.sql(dialect='sqlite'), 80))


@dataclass
class QueryContext:
    """SELECT, GROUP, ORDER, LIMIT / OFFSET and JOIN terms of one (sub-)query prefix over both queries of a pair."""
    select_refs: list = field(default_factory=list)
    group_refs: list = field(default_factory=list)
    order_terms: list = field(default_factory=list)
    ranks: list = field(default_factory=list)
    joins: list = field(default_factory=list)


EMPTY_CONTEXT = QueryContext()


def boundary_facts(side, operator, value):
    attributed = comparison_target(side, operator, value)
    return [(ref, BOUNDARY, attributed[1]) for ref in attributed[0]] if attributed else []


def join_facts(left, right):
    return [(left, UNMATCHED, (right,)), (right, UNMATCHED, (left,))]


def aggregate_boundary_facts(aggregate, operator, value, context):
    """HAVING COUNT(col) > 3: the aggregated column (COUNT(*): the GROUP columns) at the aggregate's boundary."""
    refs = column_refs(aggregate) or list(context.group_refs)
    text = shorten(aggregate.sql(dialect='sqlite'), 60)
    return [(ref, AGGREGATE_BOUNDARY, (text, operator, value)) for ref in refs]


def subquery_facts(side, subquery, semi_join_only=False):
    """col = (SELECT MAX / MIN(...)): ties at rank 1 in that direction; col = / IN (SELECT a column of another table
    ...): a semi-join edge between the two columns."""
    select = subquery_select(subquery)
    if select is None or len(select.expressions) != 1:
        return []
    projection, refs = unwrap(select.expressions[0]), column_refs(side)[:1]
    if isinstance(projection, (exp.Max, exp.Min)) and not semi_join_only:
        direction = 'DESC' if isinstance(projection, exp.Max) else 'ASC'
        return [(ref, TIES, (direction, (1,), None)) for ref in refs]
    inner = column_ref(projection) if isinstance(projection, exp.Column) and projection.table else None
    if inner is None:
        return []
    return [fact for ref in refs if ref[0] != inner[0] for fact in join_facts(ref, inner)]


def column_pair_facts(side, other, operator):
    """col_a op col_b of one row: both columns at equal and adjacent values."""
    left, right = unwrap(side), unwrap(other)
    if not all(isinstance(n, exp.Column) and n.table for n in (left, right)):
        return []
    a, b = column_ref(left), column_ref(right)
    return [(a, BOUNDARY, ('column', operator, b)), (b, BOUNDARY, ('column', _MIRRORED[operator], a))]


def comparison_facts(node, context):
    operator, side, other = _COMPARISONS[type(node)], node.this, node.expression
    if literal_value(side) is not None and literal_value(other) is None:
        side, other, operator = other, side, _MIRRORED[operator]
    value = literal_value(other)
    if value is not None:
        aggregate = aggregate_of(side)
        if aggregate is not None:
            return aggregate_boundary_facts(aggregate, operator, value, context)
        return boundary_facts(side, operator, value)
    if subquery_select(unwrap(other)) is not None:
        return subquery_facts(side, unwrap(other))
    return column_pair_facts(side, other, operator)


def like_facts(node):
    pattern = literal_value(node.expression)
    return [] if pattern is None else [(ref, LIKE, ('like', str(pattern))) for ref in column_refs(node.this)[:1]]


def in_facts(node):
    query = node.args.get('query')
    if query is not None:
        return subquery_facts(node.this, query, semi_join_only=True)
    values = [literal_value(item) for item in node.expressions]
    return [fact for value in values if value is not None for fact in boundary_facts(node.this, '=', value)]


def between_facts(node):
    facts = []
    for key, operator in (('low', '>='), ('high', '<=')):
        value = literal_value(node.args.get(key))
        if value is not None:
            facts += boundary_facts(node.this, operator, value)
    return facts


def condition_facts(tree, context):
    """Facts of the comparisons of an expression outside its sub-queries (also inside CASE, OR and NOT)."""
    facts = []
    for node in nodes_outside_subqueries(tree):
        if isinstance(node, exp.Is) and isinstance(node.expression, exp.Null):
            facts += [(ref, NULL_ROWS, ()) for ref in column_refs(node.this)[:1]]
        elif isinstance(node, (exp.Like, exp.ILike)):
            facts += like_facts(node)
        elif isinstance(node, exp.In):
            facts += in_facts(node)
        elif isinstance(node, exp.Between):
            facts += between_facts(node)
        elif type(node) in _COMPARISONS:
            facts += comparison_facts(node, context)
    return facts


def count_term_facts(node):
    """('*' | 'column' | 'distinct') COUNT terms; COUNT of another expression (CASE ...) is no NULL test."""
    inner = node.this
    if isinstance(inner, exp.Distinct):
        return [(ref, COUNT_TERM, ('distinct',)) for ref in column_refs(inner)]
    operand = unwrap(inner) if inner is not None else None
    if operand is None or isinstance(operand, exp.Star):
        return [(None, COUNT_TERM, ('*',))]
    if isinstance(operand, exp.Column) and operand.table:
        return [(column_ref(operand), COUNT_TERM, ('column',))]
    return []


def order_term(tree, context):
    """(column refs, tie_on) of one ORDER term: an aggregate ties on the GROUP columns of its query, an expression on
    its columns (tie_on names the aggregate or expression), a plain column on itself."""
    aggregate = aggregate_of(tree)
    if aggregate is not None:
        return list(context.group_refs) or column_refs(aggregate), shorten(aggregate.sql(dialect='sqlite'), 60)
    if isinstance(unwrap(tree), exp.Column):
        return column_refs(tree), None
    return column_refs(tree), shorten(tree.sql(dialect='sqlite'), 60)


def pred_facts(argument, context):
    tree = parse_argument(argument)
    return condition_facts(tree, context) if tree is not None else []


def having_facts(argument, context):
    tree = parse_argument(argument)
    facts = condition_facts(tree, context) if tree is not None else []
    return facts or [(ref, GROUP_SIZES, ()) for ref in context.group_refs]


def select_facts(argument, context):
    tree = parse_argument(argument)
    if tree is None:
        return []
    facts = condition_facts(tree, context)
    for node in nodes_outside_subqueries(tree):
        if isinstance(node, _SPREAD_AGGREGATES):
            facts += [(ref, DIFFERENT_VALUES, (type(node).__name__.upper(),)) for ref in aggregated_refs(node)]
        elif isinstance(node, exp.Count):
            facts += count_term_facts(node)
    return facts


def aggregated_refs(aggregate):
    """Columns whose values a MAX / MIN / SUM / AVG aggregates: a column or an arithmetic expression of columns; none
    for a CASE / IIF counter such as SUM(CASE WHEN age = 28 THEN 1 ELSE 0 END) (its condition is a comparison
    fact)."""
    argument = aggregate.this
    if argument is None or any(isinstance(n, (exp.Case, exp.If) + _PREDICATES)
                               for n in nodes_outside_subqueries(argument)):
        return []
    return column_refs(argument)


def group_facts(argument, _context):
    tree = parse_argument(argument)
    return [(ref, GROUP_SIZES, ()) for ref in column_refs(tree)] if tree is not None else []


def order_facts(argument, context):
    text, direction = order_parts(argument)
    tree = parse_argument(text)
    if tree is None:
        return []
    refs, tie_on = order_term(tree, context)
    return [(ref, TIES, (direction, tuple(sorted(set(context.ranks))), tie_on)) for ref in refs]


def limit_facts(argument, context, kind='LIMIT'):
    """LIMIT k / OFFSET n: ties at that rank on the ORDER columns of the query (on its SELECT columns without one)."""
    rank = limit_rank(kind, argument)
    if rank is None:
        return []
    if not context.order_terms:
        return [(ref, TIES, (UNORDERED, (rank,), None)) for ref in context.select_refs]
    facts = []
    for tree, direction in context.order_terms:
        refs, tie_on = order_term(tree, context)
        facts += [(ref, TIES, (direction, (rank,), tie_on)) for ref in refs]
    return facts


def offset_facts(argument, context):
    return limit_facts(argument, context, kind='OFFSET')


def distinct_facts(_argument, context):
    return [(ref, DUPLICATES, ()) for ref in context.select_refs]


def join_operation_facts(argument, _context):
    return join_facts(*join_refs(argument))


def table_facts(argument, context):
    """TABLE(t) / JOIN_KIND(t, LEFT): the join edges of t in the same query."""
    table = table_name(argument.split(',')[0])
    return [fact for left, right in context.joins if table in (left[0], right[0]) for fact in join_facts(left, right)]


_HANDLERS = {'PRED': pred_facts, 'HAVING': having_facts, 'SELECT': select_facts, 'GROUP': group_facts,
             'ORDER': order_facts, 'LIMIT': limit_facts, 'OFFSET': offset_facts, 'DISTINCT': distinct_facts,
             'JOIN': join_operation_facts, 'TABLE': table_facts, 'JOIN_KIND': table_facts}


def operation_facts(op, contexts):
    """(column ref, pattern, target) facts of one operation key."""
    prefix, kind, argument = split_op(op)
    handler = _HANDLERS.get(kind)
    return handler(argument, contexts.get(prefix, EMPTY_CONTEXT)) if handler else []


def query_contexts(operations):
    """QueryContext per sub-query prefix, from the operations of both queries of a pair."""
    contexts = defaultdict(QueryContext)
    for op in sorted(operations):
        prefix, kind, argument = split_op(op)
        context = contexts[prefix]
        if kind in ('SELECT', 'GROUP'):
            tree = parse_argument(argument)
            refs = context.select_refs if kind == 'SELECT' else context.group_refs
            for ref in column_refs(tree) if tree is not None else []:
                if ref not in refs:
                    refs.append(ref)
        elif kind == 'ORDER':
            text, direction = order_parts(argument)
            tree = parse_argument(text)
            if tree is not None:
                context.order_terms.append((tree, direction))
        elif kind in ('LIMIT', 'OFFSET'):
            rank = limit_rank(kind, argument)
            if rank is not None:
                context.ranks.append(rank)
        elif kind == 'JOIN':
            context.joins.append(join_refs(argument))
    return contexts


def side_facts(operations, contexts):
    return [(fact, op) for op in operations for fact in operation_facts(op, contexts)]


def resolve_count_terms(side, other):
    """COUNT terms of one side: COUNT(DISTINCT col) -> duplicates_for_distinct; COUNT(col) -> null_in_count_column
    when the other side counts * or another column."""
    other_terms = {(fact[0], fact[2][0]) for fact, _ in other if fact[1] == COUNT_TERM}
    resolved = []
    for (ref, pattern, target), op in side:
        if pattern != COUNT_TERM:
            resolved.append(((ref, pattern, target), op))
        elif target == ('distinct',):
            resolved.append(((ref, DUPLICATES, ()), op))
        elif any(term == '*' or (term == 'column' and other_ref != ref) for other_ref, term in other_terms):
            resolved.append(((ref, NULL_IN_COUNT, ()), op))
    return resolved


def as_like_literal(fact, like_refs):
    """An equality literal of a column that a LIKE pattern of the same pair tests becomes a like_near_variant
    literal."""
    ref, pattern, target = fact
    if pattern == BOUNDARY and ref in like_refs and target[0] in ('string', 'number', 'date') and target[1] in (
            '=', '<>'):
        return ref, LIKE, ('literal', str(target[2]))
    return fact


def pair_facts(gold_ops, neighbor_ops):
    """(fact, operation) list of one pair: the facts of the added and the removed operations, COUNT terms resolved
    against the other side, structural facts that both sides carry dropped."""
    contexts = query_contexts(gold_ops | neighbor_ops)
    added = side_facts(sorted(neighbor_ops - gold_ops), contexts)
    removed = side_facts(sorted(gold_ops - neighbor_ops), contexts)
    added, removed = resolve_count_terms(added, removed), resolve_count_terms(removed, added)
    like_refs = {fact[0] for fact, _ in added + removed if fact[1] == LIKE}
    added = [(as_like_literal(fact, like_refs), op) for fact, op in added]
    removed = [(as_like_literal(fact, like_refs), op) for fact, op in removed]
    shared = {fact for fact, _ in added} & {fact for fact, _ in removed}
    return [(fact, op) for fact, op in added + removed
            if fact[0] is not None and (fact[1] in VALUE_PATTERNS or fact not in shared)]


@dataclass
class PatternEvidence:
    pairs: set = field(default_factory=set)
    ops: Counter = field(default_factory=Counter)
    targets: Counter = field(default_factory=Counter)


@dataclass
class ColumnEvidence:
    info: ColumnInfo
    pairs: set = field(default_factory=set)
    patterns: dict = field(default_factory=dict)


@dataclass
class Evidence:
    columns: dict = field(default_factory=dict)
    examples: dict = field(default_factory=lambda: defaultdict(dict))
    pool: dict = field(default_factory=lambda: defaultdict(Counter))
    stats: Counter = field(default_factory=Counter)


def pair_operations(extractor, pair):
    """(gold operation keys, neighbor operation keys); None when either query does not parse."""
    try:
        return set(extractor.keys(pair['gold_sql'])), set(extractor.keys(pair['neighbor_sql']))
    except Exception:
        return None


@lru_cache(maxsize=50000)
def operation_literals(op):
    """(column ref, literal) of the comparisons and LIKE patterns of one PRED / HAVING / SELECT operation."""
    _prefix, kind, argument = split_op(op)
    tree = parse_argument(argument) if kind in ('PRED', 'HAVING', 'SELECT') else None
    literals = []
    for ref, pattern, target in condition_facts(tree, EMPTY_CONTEXT) if tree is not None else []:
        if pattern == BOUNDARY and target[0] in ('number', 'string', 'date', 'year'):
            literals.append((ref, target[2]))
        elif pattern == LIKE:
            literals.append((ref, target[1]))
    return tuple(literals)


def add_pool_literals(pool, operations, catalog):
    for op in operations:
        for ref, literal in operation_literals(op):
            info = catalog.resolve(ref)
            if info is not None:
                pool[info.name][literal] += 1


def resolved_target(pattern, target, catalog):
    """``target`` with its column references resolved (join partners as ColumnInfo, compared columns by name)."""
    if pattern == UNMATCHED:
        return (catalog.resolve(target[0]),)
    if pattern == BOUNDARY and target[0] == 'column':
        partner = catalog.resolve(target[2])
        return target[:2] + (partner.name if partner else 'a derived column',)
    return target


def resolved_facts(facts, catalog):
    """Facts whose column is a schema column, as ((ColumnInfo, pattern, target), operation)."""
    resolved = []
    for (ref, pattern, target), op in facts:
        info = catalog.resolve(ref)
        if info is not None:
            resolved.append(((info, pattern, resolved_target(pattern, target, catalog)), op))
    return resolved


def add_pair(evidence, index, facts, added_ops, removed_ops):
    """Counts one pair's facts (each operation and target once per pair) and keeps the first example delta per
    pattern and column (its relevant operations listed first)."""
    seen = set()
    for (info, pattern, target), op in facts:
        column = evidence.columns.setdefault(info.name, ColumnEvidence(info))
        column.pairs.add(index)
        record = column.patterns.setdefault(pattern, PatternEvidence())
        record.pairs.add(index)
        for key, counter, item in (((info.name, pattern, 'op', op), record.ops, op),
                                   ((info.name, pattern, 'target', target), record.targets, target)):
            if key not in seen:
                seen.add(key)
                counter[item] += 1
        example = evidence.examples[pattern].setdefault(
            info.name, {'pair': index, 'relevant': [], 'added': added_ops, 'removed': removed_ops})
        if example['pair'] == index and op not in example['relevant']:
            example['relevant'].append(op)


def collect_evidence(extractor, pairs, catalog):
    """Facts of every pair delta, attributed to schema columns, with literal-pool and coverage statistics."""
    evidence = Evidence()
    evidence.stats['pairs'] = len(pairs)
    for index, pair in enumerate(pairs):
        operations = pair_operations(extractor, pair)
        if operations is None:
            evidence.stats['parse_errors'] += 1
            continue
        gold_ops, neighbor_ops = operations
        add_pool_literals(evidence.pool, gold_ops | neighbor_ops, catalog)
        delta = gold_ops ^ neighbor_ops
        if not delta:
            evidence.stats['empty_delta'] += 1
            continue
        facts = resolved_facts(pair_facts(gold_ops, neighbor_ops), catalog)
        evidence.stats['delta_ops'] += len(delta)
        evidence.stats['delta_ops_without_target'] += len(delta - {op for _, op in facts})
        evidence.stats['pairs_with_targets'] += bool(facts)
        add_pair(evidence, index, facts, sorted(neighbor_ops - gold_ops), sorted(gold_ops - neighbor_ops))
    return evidence


def unique(values):
    out = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def tidy(number, digits):
    return int(round(number)) if digits == 0 else round(number, digits)


def plain_steps(value):
    """A literal and one step on each side (integers +-1, decimals +-0.01); a string literal alone."""
    if not isinstance(value, (int, float)):
        return [value]
    step = 1 if isinstance(value, int) else 0.01
    digits = max(decimal_places(float(step)), decimal_places(value))
    return [tidy(value - step, digits), value, tidy(value + step, digits)]


def number_boundaries(value, info, catalog):
    """A numeric literal and one step on each side: the column's observed decimal step, else 1 for whole numbers and
    0.01 for decimals; a fractional literal of an INTEGER column becomes its floor and ceiling."""
    if 'INT' in info.declared_type.upper() and isinstance(value, float) and not value.is_integer():
        return [math.floor(value), math.ceil(value)]
    observed = catalog.numeric_step(info)
    if observed is not None and observed < 1:
        step = observed
    else:
        step = 1 if isinstance(value, int) or value.is_integer() else 0.01
    digits = max(decimal_places(float(step)), decimal_places(value))
    return [tidy(value - step, digits), value, tidy(value + step, digits)]


def format_days(days, date_format):
    out = []
    for day in days:
        try:
            out.append(datetime(day.year, day.month, day.day).strftime(date_format))
        except (ValueError, OverflowError):
            continue
    return out


def year_edges(year):
    """The last day before a year, its first and last day and the first day after it."""
    if not 2 <= year <= 9998:
        return []
    return [date(year - 1, 12, 31), date(year, 1, 1), date(year, 12, 31), date(year + 1, 1, 1)]


def change_case(text):
    return text.lower() if text != text.lower() else text.upper()


def change_one_character(text):
    """``text`` with its last letter or digit shifted by one ('Trap' -> 'Traq', '1988' -> '1989')."""
    for index in range(len(text) - 1, -1, -1):
        char = text[index]
        if char.isdigit():
            return text[:index] + str((int(char) + 1) % 10) + text[index + 1:]
        if char.isascii() and char.isalpha():
            shifted = {'z': 'a', 'Z': 'A'}.get(char, chr(ord(char) + 1))
            return text[:index] + shifted + text[index + 1:]
    return text + 'x'


def near_variant(text):
    """One near-variant of a string literal: its case changed, else one character changed."""
    return change_case(text) if change_case(text) != text else change_one_character(text)


def date_prefix_values(pattern, date_format):
    """Boundary dates of a LIKE date prefix in the column's date format: '2013%' -> the year's edges, '2013-05%' ->
    the month's edges, '2013-05-29%' -> that day and one day on each side; None for any other pattern."""
    match = _DATE_PREFIX.match(pattern)
    if not match or not date_format:
        return None
    year, month, day = (int(group) if group else None for group in match.groups())
    try:
        if day:
            middle = date(year, month, day)
            return format_days([middle - ONE_DAY, middle, middle + ONE_DAY], date_format)
        if month:
            first = date(year, month, 1)
            following = (first + timedelta(days=32)).replace(day=1)
            return format_days([first - ONE_DAY, first, following - ONE_DAY, following], date_format)
    except ValueError:
        return None
    return format_days(year_edges(year), date_format)


def like_variants(pattern):
    """Variants of a LIKE pattern: '%' removed (matches), one character changed (does not match), extended at its
    open end (matches when the pattern starts or ends with '%'), case changed (LIKE ignores ASCII case, = does
    not)."""
    base = pattern.replace('%', '').replace('_', 'x')
    if pattern.endswith('%'):
        extended = base + ' x'
    elif pattern.startswith('%'):
        extended = 'x ' + base
    else:
        extended = base + 'x'
    return unique([base, change_one_character(base), extended, change_case(base)])


def boundary_values(kind, value, info, catalog):
    """Boundary values of one literal in the column's terms (numbers by their step, dates and years in the column's
    date format)."""
    if kind == 'number':
        return number_boundaries(value, info, catalog)
    if kind == 'string':
        return [value, near_variant(value)]
    date_format = catalog.date_format(info) or '%Y-%m-%d'
    if kind == 'date':
        day = date.fromisoformat(value)
        return format_days([day - ONE_DAY, day, day + ONE_DAY], date_format)
    return format_days(year_edges(value), date_format) if kind == 'year' else []


def capped_groups(groups, cap):
    """Values of whole groups (one literal with its neighbours), most frequent literal first, up to ``cap``."""
    out = []
    for group in groups:
        new = [value for value in unique(group) if value not in out]
        if out and len(out) + len(new) > cap:
            break
        out.extend(new)
    return out


def display_order(values):
    """Numbers and ISO dates sorted; other values in their order."""
    if all(isinstance(v, (int, float)) for v in values):
        return sorted(values)
    if all(isinstance(v, str) and _ISO_DATE.match(v) for v in values):
        return sorted(values)
    return values


def boundary_targets(targets, info, catalog, caps):
    groups, expressions, partners = [], OrderedDict(), []
    for target, _pairs in targets.most_common():
        if target[0] == 'column':
            partners.append(target[2])
        elif target[0] == 'expression':
            expressions.setdefault(target[3], []).append(plain_steps(target[2]))
        else:
            groups.append(boundary_values(target[0], target[2], info, catalog))
    out = OrderedDict()
    if groups:
        out['values'] = display_order(capped_groups(groups, caps['values']))
    if expressions:
        out['expression_values'] = [{'expression': text, 'values': display_order(capped_groups(steps, 6))}
                                    for text, steps in list(expressions.items())[:caps['details']]]
    if partners:
        out['equal_and_one_step_from'] = unique(partners)[:caps['details']]
    return out


def like_targets(targets, info, catalog, _caps):
    """LIKE patterns and equality literals; variants of the two most frequent patterns (date prefixes of a date
    column as boundary dates in its format)."""
    ranked = [target for target, _pairs in targets.most_common()]
    literals = unique(target[1] for target in ranked)
    date_format = catalog.date_format(info)
    variants = []
    for pattern in [target[1] for target in ranked if target[0] == 'like'][:2]:
        variants += date_prefix_values(pattern, date_format) or like_variants(pattern)
    variants = [v for v in unique(variants) if v not in literals]
    return OrderedDict([('literals', literals[:6]), ('variants', variants[:8])])


def aggregate_targets(targets, _info, _catalog, caps):
    aggregates, groups = [], []
    for (text, _operator, value), _pairs in targets.most_common():
        aggregates.append(text)
        steps = plain_steps(value)
        if text.upper().startswith('COUNT'):
            steps = [v for v in steps if not isinstance(v, (int, float)) or v >= 0]
        groups.append(steps)
    return OrderedDict([('aggregate', unique(aggregates)[:2]),
                        ('values', display_order(capped_groups(groups, caps['values'])))])


def null_targets(_targets, info, _catalog, _caps):
    return {'null_share': NULL_SHARE if info.nullable else NO_NULL}


def duplicate_targets(_targets, _info, _catalog, _caps):
    return {'duplicate_share': DUPLICATE_SHARE}


def ties_targets(targets, _info, _catalog, caps):
    ranks = sorted({rank for target in targets for rank in target[1]})
    directions = sorted({target[0] for target in targets})
    tie_on = unique(target[2] for target, _pairs in targets.most_common() if target[2])
    out = OrderedDict([('tie_at_rank', ranks[:5] or NO_LIMIT), ('direction', ' and '.join(directions))])
    if tie_on:
        out['tie_on'] = tie_on[:caps['details']]
    return out


def unmatched_targets(targets, info, catalog, _caps):
    partners = [p for p in unique(target[0] for target, _pairs in targets.most_common()) if p is not None]
    children = [catalog.child_column(info, partner) for partner in partners] or [info]
    return OrderedDict([('joins_with', [partner.name for partner in partners[:3]] or ['a derived table']),
                        ('parent_rows_without_children', True),
                        ('child_rows_with_null_fk', any(child.nullable for child in children))])


def group_targets(_targets, _info, _catalog, _caps):
    return {'group_sizes': GROUP_SIZE_TARGET}


def different_value_targets(_targets, _info, _catalog, _caps):
    return {'qualifying_rows': DIFFERENT_VALUES_TARGET}


TARGETS = {BOUNDARY: boundary_targets, LIKE: like_targets, AGGREGATE_BOUNDARY: aggregate_targets,
           NULL_IN_COUNT: null_targets, NULL_ROWS: null_targets, DUPLICATES: duplicate_targets, TIES: ties_targets,
           UNMATCHED: unmatched_targets, GROUP_SIZES: group_targets, DIFFERENT_VALUES: different_value_targets}


def render_pattern(name, record, info, catalog, caps):
    """{"pairs", "ops" (most frequent first; left out when the level shows none for the pattern), "targets"}."""
    limit = caps['value_ops'] if name in VALUE_PATTERNS else caps['other_ops']
    rendered = OrderedDict([('pairs', len(record.pairs))])
    if limit:
        rendered['ops'] = [shorten(op, caps['op_chars']) for op, _pairs in record.ops.most_common(limit)]
    rendered['targets'] = TARGETS[name](record.targets, info, catalog, caps)
    return rendered


def min_pairs(pattern, caps):
    """Pairs a pattern needs to be shown with its operations and targets at this size level."""
    return min(caps['min_pairs'], VALUE_MIN_PAIRS) if pattern in VALUE_PATTERNS else caps['min_pairs']


def render_column(column, catalog, caps):
    """{"column", "declared_type", "date_format" (date/time text only), "patterns": {pattern: {"pairs", "ops",
    "targets"}}, "minor_patterns": {pattern: pairs}}: patterns with the most pairs first; patterns below min_pairs
    (except the first) are listed with their pair count only."""
    info = column.info
    entry = OrderedDict([('column', info.name), ('declared_type', info.declared_type)])
    if catalog.date_format(info):
        entry['date_format'] = catalog.date_format(info)
    ranked = sorted(column.patterns.items(), key=lambda kv: (-len(kv[1].pairs), kv[0]))
    major = [(name, record) for i, (name, record) in enumerate(ranked)
             if i == 0 or len(record.pairs) >= min_pairs(name, caps)]
    entry['patterns'] = OrderedDict((name, render_pattern(name, record, info, catalog, caps)) for name, record in major)
    minor = OrderedDict((name, len(record.pairs)) for name, record in ranked if (name, record) not in major)
    if minor:
        entry['minor_patterns'] = minor
    return entry


def render_pool(pool, listed, caps):
    """Literals of the construction SQL for the columns without an entry (most distinct literals first)."""
    ranked = sorted(((name, counts) for name, counts in pool.items() if name not in listed),
                    key=lambda kv: (-len(kv[1]), kv[0]))
    return [{'column': name, 'count': len(counts), 'literals': [v for v, _n in counts.most_common(MAX_POOL_LITERALS)]}
            for name, counts in ranked[:caps['pool_columns']]]


def example_side(example, side, caps):
    """At most caps['example_ops'] operations of one side of an example delta: the pattern's own operations first,
    then those of the same kind (the COUNT(*) that a COUNT(col) replaced), then the others."""
    kinds = {op_kind(op) for op in example['relevant']}
    ranked = sorted(example[side], key=lambda op: (op not in example['relevant'], op_kind(op) not in kinds))
    return [shorten(op, caps['op_chars']) for op in ranked[:caps['example_ops']]]


def render_examples(examples, ranked_names, caps):
    """At most caps['examples'] (<= 2) example deltas per pattern, from the highest-ranked columns, distinct pairs."""
    out = OrderedDict()
    for pattern in PATTERN_ORDER:
        chosen, pairs = [], set()
        for name in ranked_names:
            example = examples.get(pattern, {}).get(name)
            if example and example['pair'] not in pairs and len(chosen) < caps['examples']:
                pairs.add(example['pair'])
                chosen.append({side: example_side(example, side, caps) for side in ('added', 'removed')})
        if chosen:
            out[pattern] = chosen
    return out


def render_summary(evidence, catalog, caps, level):
    ranked = sorted(evidence.columns.values(), key=lambda column: (-len(column.pairs), column.info.name))
    listed = ranked[:caps['columns']]
    names = [column.info.name for column in listed]
    return OrderedDict([('columns', [render_column(column, catalog, caps) for column in listed]),
                        ('other_columns', len(ranked) - len(listed)),
                        ('literal_pool_other_columns', render_pool(evidence.pool, set(names), caps)),
                        ('examples', render_examples(evidence.examples, names, caps)),
                        ('stats', dict(evidence.stats, columns=len(ranked), size_level=level))])


def size_budget(evidence):
    """Characters of the summary: CHARS_PER_PAIR per pair with a target, between MIN_CHARS and MAX_CHARS."""
    return min(MAX_CHARS, max(MIN_CHARS, CHARS_PER_PAIR * evidence.stats['pairs_with_targets']))


def designer_atomic_summary(compact, pairs, original=None, max_chars=None):
    """Designer input: one entry per table.column of the pair deltas (most pairs first, at most 40) with its
    patterns, operations and generation targets, a literal pool of the other columns, <= 2 example deltas per
    pattern and statistics, as compact JSON."""
    connection = sqlite3.connect('file:%s?mode=ro' % (original or compact), uri=True)
    connection.text_factory = lambda b: b.decode('utf-8', errors='replace')
    try:
        catalog = ColumnCatalog(connection)
        evidence = collect_evidence(OpExtractor(schema_columns(compact)), pairs, catalog)
        budget = max_chars or size_budget(evidence)
        for level, caps in enumerate(SIZE_LEVELS):
            summary = render_summary(evidence, catalog, caps, level)
            summary['stats']['budget_chars'] = budget
            text = json.dumps(summary, default=str, separators=(',', ':'))
            if len(text) <= budget:
                break
        return text
    finally:
        connection.close()
