"""Build the compact database D_c of one training database from its gold queries.

``--golds`` is a JSON list of the gold SQL queries of the database.  The selected rows are copied byte for byte
(ATTACH + INSERT ... SELECT) and a JSON report (row counts, selection rules, diagnostics) is written next to the
output database.
"""
import argparse
import json
import os
import sqlite3
import time
from collections import Counter
from pathlib import Path

from .slicer import RowSelector, Schema, run_probe

MASTER_ORDER = ("SELECT type, name, sql FROM src.sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
                "ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 WHEN 'view' THEN 2 ELSE 3 END")


def _remove_existing(path):
    for suffix in ('', '-wal', '-shm'):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)


def _copy_table(out, schema, table, rowids):
    real = schema.tables[table]
    columns = list(schema.columns[table].values())
    column_list = ', '.join('"%s"' % c for c in columns)
    source_list = ', '.join('s."%s"' % c for c in columns)
    out.execute('DELETE FROM temp._keep')
    out.executemany('INSERT INTO temp._keep(rid) VALUES(?)', [(r,) for r in sorted(rowids)])
    out.execute(
        'INSERT INTO main."%s"(rowid, %s) SELECT s.rowid, %s FROM src."%s" s JOIN temp._keep k ON k.rid = s.rowid' %
        (real, column_list, source_list, real))
    return out.execute('SELECT COUNT(*) FROM main."%s"' % real).fetchone()[0]


def write_compact_db(source_path, target_path, schema, keep):
    """Copy the kept rows into a new SQLite file; returns (rows per table, index errors, FK violations)."""
    _remove_existing(target_path)
    out = sqlite3.connect(target_path)
    out.isolation_level = None
    out.execute('PRAGMA foreign_keys=OFF')
    out.execute('PRAGMA journal_mode=OFF')
    out.execute('ATTACH DATABASE ? AS src', (str(source_path),))
    master = out.execute(MASTER_ORDER).fetchall()
    out.execute('BEGIN')
    for kind, _name, sql in master:
        if kind == 'table':
            out.execute(sql)
    out.execute('CREATE TEMP TABLE _keep(rid INTEGER PRIMARY KEY)')
    rows_per_table = {schema.tables[t]: _copy_table(out, schema, t, keep.get(t, ())) for t in schema.tables}
    out.execute('COMMIT')
    index_errors = []
    for kind, name, sql in master:
        if kind != 'table':
            try:
                out.execute(sql)
            except sqlite3.Error as exc:
                index_errors.append('%s:%s:%s' % (kind, name, str(exc)[:80]))
    out.execute('DROP TABLE temp._keep')
    out.execute('DETACH DATABASE src')
    violations = run_probe(out, 'PRAGMA foreign_key_check', timeout_s=120.0)
    out.execute('VACUUM')
    out.close()
    return rows_per_table, index_errors, len(violations)


def gold_support(path, golds):
    """Number of golds that return at least one non-NULL row on the database at ``path``."""
    connection = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
    supported = 0
    for gold in golds:
        rows = run_probe(connection, gold, timeout_s=30.0)
        supported += any(v is not None for row in rows for v in row)
    connection.close()
    return supported


def compact(original, golds, output, max_rounds=8, rows_per_gold=20):
    """Run row selection, referenced-row traversal and the copy; returns a report dict."""
    start = time.time()
    connection = sqlite3.connect('file:%s?mode=ro' % original, uri=True)
    connection.text_factory = lambda b: b.decode('utf-8', errors='replace')
    connection.execute('PRAGMA case_sensitive_like=ON')
    schema = Schema(connection)
    selector = RowSelector(connection, schema, rows_per_gold=rows_per_gold)
    for gold in golds:
        selector.add_gold(gold)
    selector.sample_unreferenced_tables()
    selector.add_referenced_rows(max_rounds=max_rounds)
    connection.close()
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    rows, index_errors, fk_violations = write_compact_db(original, output, schema, selector.keep)
    rules = sum((Counter(c) for c in selector.provenance.values()), Counter())
    return {
        'original': str(original), 'output': str(output), 'n_golds': len(golds),
        'original_rows': sum(schema.row_counts.values()), 'compact_rows': sum(rows.values()),
        'rows_per_table': rows, 'rows_by_rule': dict(rules), 'diagnostics': dict(selector.stats),
        'index_errors': index_errors, 'fk_violations_in_compact': fk_violations,
        'golds_supported_original': gold_support(original, golds),
        'golds_supported_compact': gold_support(output, golds),
        'original_mb': round(os.path.getsize(original) / 1e6, 3),
        'compact_mb': round(os.path.getsize(output) / 1e6, 3),
        'wall_s': round(time.time() - start, 1),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--original', required=True, help='original SQLite database (read only)')
    parser.add_argument('--golds', required=True, help='JSON list of gold SQL queries')
    parser.add_argument('--output', required=True, help='path of the compact SQLite database to write')
    parser.add_argument('--max-rounds', type=int, default=8, help='referenced-row traversal rounds')
    parser.add_argument('--rows-per-gold', type=int, default=20, help='row-lineage probe limit per gold')
    args = parser.parse_args()
    golds = json.loads(Path(args.golds).read_text())
    report = compact(args.original, golds, args.output, args.max_rounds, args.rows_per_gold)
    Path(args.output + '.report.json').write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({k: report[k] for k in ('original_rows', 'compact_rows', 'golds_supported_original',
                                             'golds_supported_compact', 'wall_s')}))


if __name__ == '__main__':
    main()
