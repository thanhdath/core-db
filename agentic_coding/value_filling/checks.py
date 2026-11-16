"""Automated checks of one generation program on the compact database (input of the Reviewer)."""
import ast
import json
import sqlite3
import tempfile
import time
from collections import Counter
from pathlib import Path

from ..common import sha_file
from ..separation import separate
from .generate import run_program


def compact_row_sets(compact):
    """{table: set of row tuples} of the compact database (to tell inherited rows from generated ones)."""
    connection = sqlite3.connect('file:%s?mode=ro' % compact, uri=True)
    try:
        tables = [r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {t: set(connection.execute('SELECT * FROM "%s"' % t)) for t in tables}
    finally:
        connection.close()


def integrity_report(path, compact_rows=None):
    """Integrity, foreign-key, NOT NULL and primary-key violations of one instance, counted on the generated rows;
    violations of rows identical to compact rows are counted apart as inherited_from_compact."""
    compact_rows = compact_rows or {}
    connection = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
    generated = {'fk_violations': 0, 'not_null_violations': 0, 'pk_duplicates': 0}
    inherited = dict(generated)

    def count(kind, table, rows):
        for row in rows:
            target = inherited if tuple(row) in compact_rows.get(table, ()) else generated
            target[kind] += 1

    try:
        fk_rows = connection.execute('PRAGMA foreign_key_check').fetchall()
    except sqlite3.OperationalError:
        fk_rows = []
    for table, rowid, _parent, _fkid in fk_rows:
        row = connection.execute('SELECT * FROM "%s" WHERE rowid = ?' % table, (rowid,)).fetchone() \
            if rowid is not None else None
        count('fk_violations', table, [row if row is not None else ('<no rowid>',)])
    report = {'integrity': connection.execute('PRAGMA integrity_check').fetchone()[0], 'rows': 0}
    tables = [r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for table in tables:
        info = connection.execute('PRAGMA table_info("%s")' % table).fetchall()
        report['rows'] += connection.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()[0]
        for column in (r[1] for r in info if r[3]):
            count('not_null_violations', table,
                  connection.execute('SELECT * FROM "%s" WHERE "%s" IS NULL' % (table, column)).fetchall())
        key_columns = [r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]]
        if key_columns:
            key = ', '.join('"%s"' % c for c in key_columns)
            for values in connection.execute('SELECT %s FROM "%s" GROUP BY %s HAVING COUNT(*) > 1'
                                             % (key, table, key)).fetchall():
                members = connection.execute('SELECT * FROM "%s" WHERE %s' % (table, ' AND '.join(
                    '"%s" IS ?' % c for c in key_columns)), values).fetchall()
                all_inherited = all(tuple(m) in compact_rows.get(table, ()) for m in members)
                (inherited if all_inherited else generated)['pk_duplicates'] += 1
    connection.close()
    report.update(generated)
    report['inherited_from_compact'] = inherited
    return report


def compact_rows_missing(path, compact):
    """Number of compact rows that an instance no longer contains unchanged (set comparison per table)."""
    connection = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
    try:
        connection.execute('ATTACH DATABASE ? AS dc', ('file:%s?mode=ro' % compact,))
        tables = [r[0] for r in connection.execute(
            "SELECT name FROM dc.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        missing = 0
        for table in tables:
            try:
                missing += connection.execute('SELECT COUNT(*) FROM (SELECT * FROM dc."%s" EXCEPT SELECT * FROM '
                                              'main."%s")' % (table, table)).fetchone()[0]
            except sqlite3.Error:
                missing += connection.execute('SELECT COUNT(*) FROM dc."%s"' % table).fetchone()[0]
        return missing
    finally:
        connection.close()


def instance_validity(units, compact, reports=None, compact_rows=None, program_instances=None):
    """Validity gate, separate from completion: an instance is valid iff it adds rows, still contains every compact
    row unchanged and its generated rows add no integrity failure (FK, NOT NULL, primary key, integrity_check)."""
    compact_rows = compact_rows if compact_rows is not None else compact_row_sets(compact)
    base, entries = _total_rows(compact), []
    for i, unit in enumerate(units):
        report = reports[i] if reports else integrity_report(unit, compact_rows)
        failures = {k: report[k] for k in ('fk_violations', 'not_null_violations', 'pk_duplicates') if report[k]}
        if report['integrity'] != 'ok':
            failures['integrity_check'] = str(report['integrity'])[:200]
        added, missing = report['rows'] - base, compact_rows_missing(unit, compact)
        reasons = [name for name, bad in (('no_rows_added', added <= 0), ('compact_rows_missing', missing > 0),
                                          ('new_integrity_failures', bool(failures))) if bad]
        entry = {'unit': Path(unit).name, 'valid': not reasons, 'reasons': reasons, 'rows_added': added,
                 'compact_rows_missing': missing, 'new_integrity_failures': failures}
        program = (program_instances or {}).get(Path(unit).name) or (program_instances or {}).get(Path(unit).stem)
        if isinstance(program, dict):
            entry['program'] = {k: program.get(k) for k in ('rows_added', 'rows_skipped', 'errors')}
        entries.append(entry)
    invalid = [e for e in entries if not e['valid']]
    summary = {'valid': len(entries) - len(invalid), 'invalid': len(invalid),
               'reasons': dict(Counter(r for e in invalid for r in e['reasons'])), 'invalid_examples': invalid[:5]}
    return entries, summary


def nullable_columns(compact, units):
    """One line per nullable column (NOT NULL and primary-key columns excluded) with the generated rows (instance
    rows above the compact maximum rowid of the table) pooled over the instances: "<table>.<column>: generated
    rows: NULL <k> / <n>"; columns without NULL rows first."""
    connection = sqlite3.connect('file:%s?mode=ro' % compact, uri=True)
    try:
        tables = [r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        columns = {t: [r[1] for r in connection.execute('SELECT * FROM pragma_table_info(?)', (t,))
                       if not r[3] and not r[5]] for t in tables}
        maxima = {t: connection.execute('SELECT COALESCE(MAX(rowid), 0) FROM "%s"' % t).fetchone()[0]
                  for t in tables if columns[t]}
    except sqlite3.Error:
        return []
    finally:
        connection.close()
    counts = {}
    for unit in units:
        try:
            connection = sqlite3.connect('file:%s?mode=ro' % unit, uri=True)
        except sqlite3.Error:
            continue
        try:
            for table, maximum in maxima.items():
                parts = ', '.join('SUM("%s" IS NULL)' % c for c in columns[table])
                row = connection.execute('SELECT COUNT(*), %s FROM "%s" WHERE rowid > ?' % (parts, table),
                                         (maximum,)).fetchone()
                for column, nulls in zip(columns[table], row[1:]):
                    total = counts.setdefault((table, column), [0, 0])
                    total[0], total[1] = total[0] + (nulls or 0), total[1] + row[0]
        except sqlite3.Error:
            continue
        finally:
            connection.close()
    lines = [(k > 0, '%s.%s: generated rows: NULL %d / %d' % (t, c, k, n)) for (t, c), (k, n) in counts.items() if n]
    return [text for _, text in sorted(lines)]


def _total_rows(path):
    connection = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
    try:
        tables = [r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return sum(connection.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0] for t in tables)
    finally:
        connection.close()


EXPECTED_LAYOUT = '<root>/<ds>/<db>__<tag>_NNNN/<db>__<tag>_NNNN.sqlite (one directory per instance)'


def error_locations(diag_file, limit=5):
    """The exceptions the program reported while handling them (or raised uncaught) in the check run, with the file
    and line inside the program package and the innermost frames (from diag_hook/sitecustomize.py)."""
    path = Path(diag_file)
    if not path.exists():
        return []
    firsts, counts = {}, Counter()
    for line in path.read_text(errors='replace').splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get('event') == 'first':
            key = (entry['exception'], tuple((f['file'], f['line']) for f in entry['frames']))
            firsts.setdefault(key, entry)
        elif entry.get('event') == 'count':
            counts[(entry['exception'], tuple(tuple(x) for x in entry['location']))] += entry['count']
    out = []
    for key, entry in firsts.items():
        inner = entry['frames'][-1] if entry['frames'] else {}
        out.append({'exception': entry['message'], 'count': counts.get(key) or 1, 'how': entry['how'],
                    'location': '%s:%s' % (inner.get('file'), inner.get('line')), 'code': inner.get('code'),
                    'traceback': ['%s:%s in %s: %s' % (f['file'], f['line'], f['function'], f['code'])
                                  for f in entry['frames']]})
    return sorted(out, key=lambda e: -e['count'])[:limit]


def has_main_entry(program_dir):
    """True when tscore_gen/cli.py has an ``if __name__ == '__main__':`` block (``python -m tscore_gen.cli`` runs it)."""
    try:
        tree = ast.parse((Path(program_dir) / 'tscore_gen' / 'cli.py').read_text())
    except (OSError, SyntaxError, ValueError):
        return False
    return any(isinstance(node, ast.If) and '__name__' in ast.dump(node.test) and '__main__' in ast.dump(node.test)
               for node in tree.body)


def _schema_facts(connection, schema='main'):
    tables = [r[0] for r in connection.execute(
        "SELECT name FROM %s.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%%'" % schema)]
    info = {t: connection.execute('PRAGMA %s.table_info("%s")' % (schema, t)).fetchall() for t in tables}
    keys = {t: [r[1] for r in sorted(info[t], key=lambda r: r[5]) if r[5]] for t in tables}
    notnull = {t: [r[1] for r in info[t] if r[3]] for t in tables}
    fks, lower = {}, {t.lower(): t for t in tables}
    for t in tables:
        for fk in connection.execute('PRAGMA %s.foreign_key_list("%s")' % (schema, t)).fetchall():
            entry = fks.setdefault((t, fk[0]), {'parent': fk[2], 'from': [], 'to': []})
            entry['from'].append(fk[3])
            entry['to'].append(fk[4])
    for entry in fks.values():
        if any(c is None for c in entry['to']):
            entry['to'] = keys.get(lower.get(str(entry['parent']).lower()), []) or ['?']
    return tables, keys, notnull, fks


def _duplicate_groups(connection, schema, table, key):
    if not key:
        return 0
    cols = ', '.join('"%s"' % c for c in key)
    return connection.execute('SELECT COUNT(*) FROM (SELECT 1 FROM %s."%s" GROUP BY %s HAVING COUNT(*) > 1)'
                              % (schema, table, cols)).fetchone()[0]


def instance_facts(units, compact, compact_rows=None, validity_entries=None, limit=5):
    """Per instance: valid, rows added, D_c rows missing or changed, new foreign-key violations, new duplicate keys
    and new NOT NULL violations (rows identical to D_c rows are not counted); and the totals per named constraint
    over the instances (child column -> parent, table key, table), largest first."""
    compact_rows = compact_rows if compact_rows is not None else compact_row_sets(compact)
    valid = {e['unit']: e.get('valid') for e in validity_entries or []}
    totals = {'foreign_keys': Counter(), 'duplicate_keys': Counter(), 'dc_rows_missing_or_changed': Counter(),
              'not_null': Counter()}
    seen = {k: Counter() for k in totals}
    rows = []
    for unit in units:
        connection = sqlite3.connect('file:%s?mode=ro' % unit, uri=True)
        try:
            connection.execute('ATTACH DATABASE ? AS dc', ('file:%s?mode=ro' % compact,))
            tables, keys, notnull, fks = _schema_facts(connection, 'dc')
            fact = {'unit': Path(unit).name, 'valid': valid.get(Path(unit).name), 'rows_added': 0,
                    'dc_rows_missing_or_changed': 0, 'new_fk_violations': 0, 'new_duplicate_keys': 0,
                    'new_not_null_violations': 0}
            local = {k: Counter() for k in totals}
            for t in tables:
                try:
                    fact['rows_added'] += (connection.execute('SELECT COUNT(*) FROM main."%s"' % t).fetchone()[0]
                                           - connection.execute('SELECT COUNT(*) FROM dc."%s"' % t).fetchone()[0])
                    missing = connection.execute('SELECT COUNT(*) FROM (SELECT * FROM dc."%s" EXCEPT SELECT * FROM '
                                                 'main."%s")' % (t, t)).fetchone()[0]
                    dup = _duplicate_groups(connection, 'main', t, keys[t]) - _duplicate_groups(connection, 'dc', t,
                                                                                                keys[t])
                    for column in notnull[t]:
                        new_nulls = (connection.execute('SELECT COUNT(*) FROM main."%s" WHERE "%s" IS NULL'
                                                        % (t, column)).fetchone()[0]
                                     - connection.execute('SELECT COUNT(*) FROM dc."%s" WHERE "%s" IS NULL'
                                                          % (t, column)).fetchone()[0])
                        if new_nulls > 0:
                            local['not_null']['%s.%s' % (t, column)] += new_nulls
                except sqlite3.Error as exc:
                    missing = len(compact_rows.get(t, ()))
                    dup = 0
                    local['dc_rows_missing_or_changed']['%s (%s)' % (t, str(exc)[:60])] += 0
                if missing:
                    local['dc_rows_missing_or_changed'][t] += missing
                if dup > 0:
                    local['duplicate_keys']['%s(%s)' % (t, ', '.join(keys[t]))] += dup
            try:
                violations = connection.execute('PRAGMA main.foreign_key_check').fetchall()
            except sqlite3.OperationalError as exc:
                violations = []
                local['foreign_keys']['foreign_key_check not possible: %s' % str(exc)[:80]] += 0
            for table, rowid, parent, fkid in violations:
                row = connection.execute('SELECT * FROM main."%s" WHERE rowid = ?' % table, (rowid,)).fetchone() \
                    if rowid is not None else None
                if row is not None and tuple(row) in compact_rows.get(table, ()):
                    continue
                fk = fks.get((table, fkid)) or {'parent': parent, 'from': ['?'], 'to': ['?']}
                local['foreign_keys']['%s.%s -> %s.%s' % (table, ','.join(fk['from']), fk['parent'],
                                                          ','.join(fk['to']))] += 1
        finally:
            connection.close()
        fact['dc_rows_missing_or_changed'] = sum(local['dc_rows_missing_or_changed'].values())
        fact['new_fk_violations'] = sum(local['foreign_keys'].values())
        fact['new_duplicate_keys'] = sum(local['duplicate_keys'].values())
        fact['new_not_null_violations'] = sum(local['not_null'].values())
        rows.append(fact)
        for kind in totals:
            totals[kind].update(local[kind])
            seen[kind].update({k: 1 for k in local[kind]})
    constraints = {kind: [{'constraint': k, 'rows': v, 'instances': seen[kind][k]}
                          for k, v in totals[kind].most_common(limit)] for kind in totals}
    return rows, constraints


def run_report(code, stdout, stderr, units, n_units, program_dir, locations, validity=None):
    """Plain statements for the Reviewer: what the check run did and what it produced."""
    lines = ['exit code %s; %d of %d instance directories written (expected layout %s)' % (
        code, len(units), n_units, EXPECTED_LAYOUT.replace('<tag>', 'chk'))]
    try:
        summary = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else None
    except (ValueError, IndexError):
        summary = None
    if isinstance(summary, dict) and ('n_ok' in summary or 'n_fail' in summary):
        lines.append('the program reports n_ok %s, n_fail %s, errors %s' % (
            summary.get('n_ok'), summary.get('n_fail'), json.dumps(summary.get('errors'))[:200]))
    if code == 0 and not units and not stdout.strip() and not stderr.strip():
        lines.append('the program exited 0, printed nothing and wrote 0 instance directories')
    if not has_main_entry(program_dir):
        lines.append("tscore_gen/cli.py has no `if __name__ == '__main__':` block, so `python -m tscore_gen.cli "
                     "generate ...` only defines its functions and exits without generating anything")
    if code not in (0, None):
        lines.append('the program exited with code %s (Python traceback in stderr_tail)' % code)
    for loc in locations[:3]:
        lines.append('%s x%d at %s: %s' % (loc['exception'], loc['count'], loc['location'], loc['code']))
    if not units:
        lines.append('this check produced no instance')
    elif validity is not None:
        lines.append('valid instances %s of %d (an instance is valid when it adds rows, keeps every D_c row unchanged '
                     'and adds no integrity failure); invalid reasons %s' % (
                         validity.get('valid'), len(units), json.dumps(validity.get('reasons'))))
    return lines


def construction_feedback(program_dir, db, ds, original, compact, pool, pairs, n_units=20, procs=2, workers=2, eligible=None):
    """All automated checks of one program as a JSON-serialisable dict."""
    with tempfile.TemporaryDirectory() as workdir:
        started = time.time()
        diag = Path(workdir) / 'diag.jsonl'
        code, stdout, stderr, units = run_program(program_dir, ds, db, compact, pool, Path(workdir) / 'a', n_units,
                                                  procs=procs, tag='chk', timeout=900, diag_file=diag)
        lines = stdout.strip().splitlines()
        locations = error_locations(diag)
        feedback = {'returncode': code, 'summary': lines[-1] if lines else '', 'stderr_tail': stderr[-2000:],
                    'n_instances': len(units), 'run_seconds': round(time.time() - started, 1),
                    'run_report': run_report(code, stdout, stderr, units, n_units, program_dir, locations),
                    'error_locations': locations}
        try:
            reported = int(json.loads(lines[-1]).get('n_ok') or 0) if lines else 0
        except (ValueError, TypeError, AttributeError):
            reported = 0
        if code == 0 and not units and reported:
            root = Path(workdir) / 'a'
            found = sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_dir())[:10]
            feedback['instances_not_found'] = {
                'program_reported_built': reported,
                'expected_layout': '<root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite (one directory per instance)',
                'directories_found': found}
        if code != 0 or not units:
            return feedback
        _, _, _, again = run_program(program_dir, ds, db, compact, pool, Path(workdir) / 'b', 1, tag='chk',
                                     timeout=900)
        feedback['reproducible'] = bool(again) and sha_file(again[0]) == sha_file(units[0])
        compact_rows = compact_row_sets(compact)
        reports = [integrity_report(u, compact_rows) for u in units]
        feedback['integrity'] = {key: sum(r[key] or 0 for r in reports)
                                 for key in ('fk_violations', 'not_null_violations', 'pk_duplicates')}
        feedback['integrity']['not_ok'] = sum(r['integrity'] != 'ok' for r in reports)
        entries, validity = instance_validity(units, compact, reports, compact_rows)
        feedback['validity'] = {k: validity.get(k) for k in ('valid', 'invalid', 'reasons')}
        feedback['instances'], feedback['constraint_violations'] = instance_facts(units, compact, compact_rows,
                                                                                  entries)
        feedback['run_report'] = run_report(code, stdout, stderr, units, n_units, program_dir, locations,
                                            feedback['validity'])
        feedback['nullable_columns'] = nullable_columns(compact, units)
        eligible, separated, unknown = separate(original, [str(compact)] + units, pairs, workers, eligible)
        separable = set().union(*separated.values()) if separated else set()
        feedback['construction_pairs'] = {'eligible': len(eligible), 'separated': len(separable),
                                          'unknown_executions': sum(unknown.values())}
    return feedback
