"""Minimal row selection and referenced-row traversal (paper Section "Database Compaction").

For every gold query the slicer maps a bounded part of the query's computation to source rows
(row lineage): it re-runs the gold's FROM/JOIN/WHERE with the rowids of every source table projected,
and adds bounded probes for ORDER BY extremes, GROUP BY groups, join fan-out and comparison
boundaries.  Referenced rows are then added by following foreign keys from referencing to referenced
tables until no new row is added or ``max_rounds`` is reached.

The slicer only reads the original database; ``compact.write_compact_db`` writes the copy.
"""
from collections import Counter, defaultdict
import time

import sqlglot
from sqlglot import exp

CHUNK = 800
PROBE_TIMEOUT_S = 8.0
COMPARISONS = {exp.EQ: '=', exp.NEQ: '!=', exp.GT: '>', exp.GTE: '>=', exp.LT: '<', exp.LTE: '<=',
               exp.Like: 'LIKE'}


def run_probe(connection, sql, params=(), timeout_s=PROBE_TIMEOUT_S):
    """Run a probe query; any failure (timeout, bad SQL, missing column) returns []."""
    deadline = time.time() + timeout_s
    connection.set_progress_handler(lambda: 1 if time.time() >= deadline else 0, 2000)
    try:
        return connection.execute(sql, params).fetchall()
    except Exception:
        return []
    finally:
        connection.set_progress_handler(None, 0)


def sql_literal(value):
    """Render a Python value as an SQLite literal."""
    if value is None:
        return 'NULL'
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


class Schema:
    """Tables, columns, primary keys, foreign keys and row counts of one SQLite database."""

    def __init__(self, connection):
        self.tables = {}                 # lower name -> real name
        self.columns = {}                # lower table -> {lower column -> real column}
        self.primary_keys = {}           # lower table -> [real column]
        self.foreign_keys = defaultdict(list)  # lower child -> [(lower parent, [(child col, parent col)])]
        self.row_counts = {}
        names = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        for (name,) in names:
            self._read_table(connection, name)
        for lower, name in self.tables.items():
            self._read_foreign_keys(connection, lower, name)

    def _read_table(self, connection, name):
        info = connection.execute('PRAGMA table_info("%s")' % name).fetchall()
        lower = name.lower()
        self.tables[lower] = name
        self.columns[lower] = {row[1].lower(): row[1] for row in info}
        self.primary_keys[lower] = [row[1] for row in sorted(info, key=lambda r: r[5]) if row[5]]
        self.row_counts[lower] = connection.execute('SELECT COUNT(*) FROM "%s"' % name).fetchone()[0]

    def _read_foreign_keys(self, connection, lower, name):
        groups = defaultdict(list)
        for row in connection.execute('PRAGMA foreign_key_list("%s")' % name).fetchall():
            groups[row[0]].append(row)
        for rows in groups.values():
            parent = (rows[0][2] or '').lower()
            if parent not in self.tables:
                continue
            parent_key = self.primary_keys[parent]
            pairs = []
            for i, row in enumerate(sorted(rows, key=lambda r: r[1])):
                child_col = row[3]
                parent_col = row[4] if row[4] is not None else (parent_key[i] if i < len(parent_key) else None)
                if child_col is None or parent_col is None:
                    pairs = []
                    break
                pairs.append((child_col, parent_col))
            if pairs:
                self.foreign_keys[lower].append((parent, pairs))

    def real(self, lower):
        """Real table name for a lower-case name (None if unknown)."""
        return self.tables.get(lower)


def parse_sql(sql):
    """Parse one SQLite query with sqlglot; None when it cannot be parsed."""
    try:
        return sqlglot.parse_one(sql, read='sqlite')
    except Exception:
        return None


def source_tables(select):
    """[(alias, table)] when every FROM/JOIN source of ``select`` is a base table, else None."""
    from_clause = select.args.get('from') or select.args.get('from_')
    if from_clause is None:
        return None
    sources = [from_clause.this] + [join.this for join in select.args.get('joins') or []]
    if not all(isinstance(s, exp.Table) for s in sources):
        return None
    return [(s.alias_or_name, s.name) for s in sources]


def from_join_sql(select):
    """("FROM ... JOIN ...", {alias_lower: table_lower}) or (None, {})."""
    tables = source_tables(select)
    from_clause = select.args.get('from') or select.args.get('from_')
    if not tables or from_clause is None:
        return None, {}
    try:
        parts = [from_clause.sql(dialect='sqlite')]
        parts += [join.sql(dialect='sqlite') for join in select.args.get('joins') or []]
    except Exception:
        return None, {}
    return ' '.join(parts), {alias: table.lower() for alias, table in tables}


def clause_sql(select, key):
    """' WHERE ...' / ' ORDER BY ...' of ``select`` or ''."""
    node = select.args.get(key)
    if node is None:
        return ''
    try:
        return ' ' + node.sql(dialect='sqlite')
    except Exception:
        return ''


def comparison_triples(tree):
    """[(column, operator, literal value)] for every column-vs-literal comparison of the query."""
    triples = set()
    for node_type, op in COMPARISONS.items():
        for node in tree.find_all(node_type):
            left, right = node.this, node.expression
            if isinstance(right, exp.Column) and isinstance(left, exp.Literal):
                left, right = right, left
            if isinstance(left, exp.Column) and isinstance(right, exp.Literal):
                value = right.this if right.is_string else _number(right.this)
                if value is not None:
                    triples.add((left.name, op, value))
    return sorted(triples, key=repr)


def _number(text):
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return None


def join_edges(select, alias_map):
    """[(alias_a, column_a, alias_b, column_b)] of every equality in the ON clauses."""
    edges = []
    for join in select.args.get('joins') or []:
        on = join.args.get('on')
        if on is None:
            continue
        for equality in on.find_all(exp.EQ):
            left, right = equality.this, equality.expression
            if isinstance(left, exp.Column) and isinstance(right, exp.Column):
                if (left.table or '') in alias_map and (right.table or '') in alias_map:
                    edges.append((left.table, left.name, right.table, right.name))
    return edges


class RowSelector:
    """Collects the rowids to keep per table (minimal row selection + referenced rows)."""

    def __init__(self, connection, schema, rows_per_gold=20, n_groups=4, base_sample=5,
                 unreferenced_sample=20, per_gold_budget_s=6.0):
        self.connection = connection
        self.schema = schema
        self.rows_per_gold = rows_per_gold
        self.n_groups = n_groups
        self.base_sample = base_sample
        self.unreferenced_sample = unreferenced_sample
        self.per_gold_budget_s = per_gold_budget_s
        self.keep = defaultdict(set)
        self.provenance = defaultdict(Counter)
        self.stats = Counter()
        self.referenced = set()

    def add(self, table, rowids, rule):
        """Keep ``rowids`` of ``table`` and record the rule that selected them."""
        if table not in self.schema.tables:
            return
        new = set(rowids) - self.keep[table]
        if new:
            self.keep[table] |= new
            self.provenance[table][rule] += len(new)

    def harvest(self, from_sql, alias_map, where, extra='', tail='', limit=None, rule='filter'):
        """Row lineage: project the rowid of every source table of FROM/JOIN/WHERE and keep them."""
        aliases = list(alias_map)
        projection = ', '.join('"%s".rowid' % a for a in aliases)
        if extra:
            where = (where + ' AND ' + extra) if where.strip() else ' WHERE ' + extra
        sql = 'SELECT DISTINCT %s %s%s%s LIMIT %d' % (projection, from_sql, where, tail,
                                                      limit or self.rows_per_gold)
        rows = run_probe(self.connection, sql)
        if not rows:
            self.stats['empty_' + rule] += 1
            return 0
        for i, alias in enumerate(aliases):
            self.add(alias_map[alias], [r[i] for r in rows if r[i] is not None], rule)
        return len(rows)

    def select_order_extremes(self, select, from_sql, alias_map, where):
        """Rows returned at both ends of the gold's ORDER BY."""
        order = clause_sql(select, 'order')
        if not order:
            return
        half = max(1, self.rows_per_gold // 2)
        self.harvest(from_sql, alias_map, where, tail=order, limit=half, rule='order_top')
        flipped = order.replace(' DESC', ' \x00').replace(' ASC', ' DESC').replace(' \x00', ' ASC')
        if flipped == order:
            flipped = order + ' DESC'
        self.harvest(from_sql, alias_map, where, tail=flipped, limit=half, rule='order_bottom')

    def select_groups(self, select, from_sql, alias_map, where):
        """Complete witnesses for up to ``n_groups`` groups of the gold's GROUP BY."""
        group = select.args.get('group')
        if group is None:
            return
        columns = [e for e in group.expressions if isinstance(e, exp.Column)]
        if not columns:
            return
        keys = ', '.join(e.sql(dialect='sqlite') for e in columns)
        values = run_probe(self.connection, 'SELECT %s %s%s GROUP BY %s LIMIT %d'
                           % (keys, from_sql, where, keys, self.n_groups))
        per_group = max(2, self.rows_per_gold // max(1, len(values)))
        for value in values:
            condition = ' AND '.join('(%s IS %s)' % (e.sql(dialect='sqlite'), sql_literal(v))
                                     for e, v in zip(columns, value))
            self.harvest(from_sql, alias_map, where, extra=condition, limit=per_group, rule='group')

    def select_join_fanout(self, select, alias_map):
        """For each join edge, a key value that matches at least two rows on one side."""
        for left_alias, left_col, right_alias, right_col in join_edges(select, alias_map):
            for a, ca, b, cb in ((left_alias, left_col, right_alias, right_col),
                                 (right_alias, right_col, left_alias, left_col)):
                self._fanout_pair(alias_map[a], ca, alias_map[b], cb)

    def _fanout_pair(self, table_a, column_a, table_b, column_b):
        real_a, real_b = self.schema.real(table_a), self.schema.real(table_b)
        col_a = self.schema.columns.get(table_a, {}).get(column_a.lower())
        col_b = self.schema.columns.get(table_b, {}).get(column_b.lower())
        if not (real_a and real_b and col_a and col_b):
            return
        value = run_probe(self.connection,
                          'SELECT b."%s" FROM "%s" b JOIN "%s" a ON a."%s" = b."%s" WHERE b."%s" IS NOT NULL '
                          'GROUP BY b."%s" HAVING COUNT(*) >= 2 LIMIT 1'
                          % (col_b, real_b, real_a, col_a, col_b, col_b, col_b))
        if not value:
            self.stats['no_fanout_pair'] += 1
            return
        for table, real, col in ((table_b, real_b, col_b), (table_a, real_a, col_a)):
            rows = run_probe(self.connection, 'SELECT rowid FROM "%s" WHERE "%s" IS ? LIMIT 4' % (real, col),
                             (value[0][0],))
            self.add(table, [r[0] for r in rows], 'join_fanout')

    def select_boundaries(self, tree, alias_map):
        """Rows just below, at and just above every comparison literal."""
        tables = list(dict.fromkeys(alias_map.values()))
        for column, _op, value in comparison_triples(tree):
            if isinstance(value, str):
                value = value.replace('%', '').replace('_', '')
                if not value:
                    continue
            for table in tables:
                real_col = self.schema.columns.get(table, {}).get(column.lower())
                if real_col:
                    self._boundary_rows(table, real_col, value)

    def _boundary_rows(self, table, column, value):
        real = self.schema.real(table)
        probes = {
            'boundary_low': 'SELECT rowid FROM "%s" WHERE "%s" IS NOT NULL AND "%s" < ? ORDER BY "%s" DESC LIMIT 2',
            'boundary_high': 'SELECT rowid FROM "%s" WHERE "%s" IS NOT NULL AND "%s" > ? ORDER BY "%s" ASC LIMIT 2',
        }
        for rule, template in probes.items():
            rows = run_probe(self.connection, template % (real, column, column, column), (value,))
            self.add(table, [r[0] for r in rows], rule)
        rows = run_probe(self.connection, 'SELECT rowid FROM "%s" WHERE "%s" IS ? LIMIT 2' % (real, column), (value,))
        self.add(table, [r[0] for r in rows], 'boundary_equal')

    def add_gold(self, gold_sql):
        """Apply every selection rule to every SELECT block of one gold query."""
        tree = parse_sql(gold_sql)
        if tree is None:
            self.stats['parse_fail'] += 1
            return
        self.referenced |= {t.name.lower() for t in tree.find_all(exp.Table)} & set(self.schema.tables)
        start = time.time()
        for select in tree.find_all(exp.Select):
            if time.time() - start > self.per_gold_budget_s:
                self.stats['gold_budget_exhausted'] += 1
                break
            from_sql, alias_map = from_join_sql(select)
            if from_sql is None or any(t not in self.schema.tables for t in alias_map.values()):
                continue
            self._select_for_block(tree, select, from_sql, alias_map)

    def _select_for_block(self, tree, select, from_sql, alias_map):
        where = clause_sql(select, 'where')
        if self.harvest(from_sql, alias_map, where, rule='filter') == 0 and where:
            self.harvest(from_sql, alias_map, '', limit=max(4, self.rows_per_gold // 4), rule='filter_fallback')
        self.select_order_extremes(select, from_sql, alias_map, where)
        self.select_groups(select, from_sql, alias_map, where)
        self.select_join_fanout(select, alias_map)
        self.select_boundaries(tree, alias_map)
        for table in set(alias_map.values()):
            if len(self.keep[table]) < self.base_sample:
                rows = run_probe(self.connection, 'SELECT rowid FROM "%s" LIMIT %d'
                                 % (self.schema.real(table), self.base_sample))
                self.add(table, [r[0] for r in rows], 'base_sample')

    def sample_unreferenced_tables(self):
        """A few rows of every table no gold reads, so no table is left empty."""
        for table in self.schema.tables:
            if table in self.referenced and self.keep[table]:
                continue
            rows = run_probe(self.connection, 'SELECT rowid FROM "%s" LIMIT %d'
                             % (self.schema.real(table), self.unreferenced_sample))
            self.add(table, [r[0] for r in rows], 'unreferenced_sample')

    def add_referenced_rows(self, max_rounds=8, non_unique_cap=200):
        """Schema-graph traversal: copy the referenced row of every kept foreign-key value."""
        for round_index in range(1, max_rounds + 1):
            added = sum(self._close_edge(child, parent, pairs, non_unique_cap)
                        for child, links in self.schema.foreign_keys.items()
                        for parent, pairs in links)
            self.stats['fk_rounds'] = round_index
            if added == 0:
                return

    def _close_edge(self, child, parent, pairs, non_unique_cap):
        rowids = sorted(self.keep.get(child, ()))
        if not rowids:
            return 0
        on = ' AND '.join('p."%s" = c."%s"' % (pc, cc) for cc, pc in pairs)
        not_null = ' AND '.join('c."%s" IS NOT NULL' % cc for cc, _ in pairs)
        unique_parent = [pc for _, pc in pairs] == self.schema.primary_keys.get(parent)
        found = set()
        for i in range(0, len(rowids), CHUNK):
            chunk = rowids[i:i + CHUNK]
            limit = '' if unique_parent else ' LIMIT %d' % non_unique_cap
            sql = ('SELECT DISTINCT p.rowid FROM "%s" p JOIN "%s" c ON %s WHERE c.rowid IN (%s) AND %s%s'
                   % (self.schema.real(parent), self.schema.real(child), on, ','.join('?' * len(chunk)),
                      not_null, limit))
            found |= {r[0] for r in run_probe(self.connection, sql, tuple(chunk), timeout_s=30.0)}
        before = len(self.keep[parent])
        self.add(parent, found, 'referenced_row')
        return len(self.keep[parent]) - before
