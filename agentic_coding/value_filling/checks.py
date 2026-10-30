"""Automated checks of one generation program on the compact database (input of the Reviewer).

Run status (failures per exception type), integrity of every instance (integrity_check, foreign keys, NOT NULL,
primary keys), reproducibility (instance 0 generated twice) and how many eligible construction pairs the instances
separate.  Only construction pairs are used; held-out pairs and labels never enter the feedback.
"""
import sqlite3
import tempfile
from pathlib import Path

from ..common import sha_file
from ..separation import separate
from .generate import run_program


def integrity_report(path):
    """Integrity, foreign-key, NOT NULL and primary-key violations of one instance."""
    connection = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
    report = {'integrity': connection.execute('PRAGMA integrity_check').fetchone()[0],
              'fk_violations': len(connection.execute('PRAGMA foreign_key_check').fetchall()),
              'not_null_violations': 0, 'pk_duplicates': 0, 'rows': 0}
    tables = [r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for table in tables:
        info = connection.execute('PRAGMA table_info("%s")' % table).fetchall()
        report['rows'] += connection.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()[0]
        for column in (r[1] for r in info if r[3]):
            report['not_null_violations'] += connection.execute(
                'SELECT COUNT(*) FROM "%s" WHERE "%s" IS NULL' % (table, column)).fetchone()[0]
        key = ', '.join('"%s"' % r[1] for r in sorted(info, key=lambda r: r[5]) if r[5])
        if key:
            report['pk_duplicates'] += connection.execute(
                'SELECT COUNT(*) FROM (SELECT %s FROM "%s" GROUP BY %s HAVING COUNT(*) > 1)'
                % (key, table, key)).fetchone()[0]
    connection.close()
    return report


def construction_feedback(program_dir, db, ds, original, compact, pool, pairs, n_units=20):
    """All automated checks of one program, as a JSON-serialisable dict."""
    with tempfile.TemporaryDirectory() as workdir:
        code, stdout, stderr, units = run_program(program_dir, ds, db, compact, pool, Path(workdir) / 'a', n_units,
                                                  tag='chk', timeout=900)
        lines = stdout.strip().splitlines()
        feedback = {'returncode': code, 'summary': lines[-1] if lines else '', 'stderr_tail': stderr[-2000:],
                    'n_instances': len(units)}
        if code != 0 or not units:
            return feedback
        _, _, _, again = run_program(program_dir, ds, db, compact, pool, Path(workdir) / 'b', 1, tag='chk',
                                     timeout=900)
        feedback['reproducible'] = bool(again) and sha_file(again[0]) == sha_file(units[0])
        reports = [integrity_report(u) for u in units]
        feedback['integrity'] = {key: sum(r[key] for r in reports)
                                 for key in ('fk_violations', 'not_null_violations', 'pk_duplicates')}
        feedback['integrity']['not_ok'] = sum(r['integrity'] != 'ok' for r in reports)
        eligible, separated, unknown = separate(original, [str(compact)] + units, pairs, workers=2)
        separable = set().union(*separated.values()) if separated else set()
        feedback['construction_pairs'] = {'eligible': len(eligible), 'separated': len(separable),
                                          'unknown_executions': sum(unknown.values())}
    return feedback
