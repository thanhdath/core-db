"""Sample candidate database instances with a generation program (package ``tscore_gen``, no LLM call)."""
import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ..common import save_json, sha_file

RELEASED = Path(__file__).resolve().parents[2] / 'value_filling_by_agents'


PROGRAM_INTERFACE = """Program interface (also given to the Engineer):
  python -m tscore_gen.cli generate --db <db_id> --orig <compact.sqlite> --ds <bird|spider> --root <out_root>
      --pool-sqls <pool_sqls.json> --i0 0 --i1 <N> --seed-base 42 --procs <P> --tag <tag>
- tscore_gen/cli.py parses exactly this command line with an argparse subcommand "generate";
- pure Python (standard library + sqlparse), no LLM or network call; the compact database is only read;
- instance i is written atomically to <root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite with only
  random.Random(seed_base * 100003 + i): a copy of the compact database plus appended generated rows, so the same
  seed gives the same file; instances keep the schema and keys; compact rows are never deleted or changed;
- the program reads the schema of the compact database: column types, primary keys, foreign keys (an inline
  reference without a column names the parent's same-name column), UNIQUE constraints including composite keys and
  CREATE UNIQUE INDEX, CHECK constraints, and fills the tables in foreign-key order;
- --pool-sqls is a JSON list of construction SQL; the literals of its comparisons, IN lists, BETWEEN and LIKE are
  typed, routed to their columns and added to the value pools (the program never executes pool SQL);
- per column and instance, values come from observed values and pool literals plus fresh values with perturbations
  (numbers +-1 / +-2, strings with prefix / suffix / dropped-character variants and LIKE patterns without '%'), a
  random cap on distinct fresh values (ties, duplicates); table sizes vary per instance (0-230 rows per table, or
  level x 4 rows per parent level up to 2,500);
- foreign-key columns draw from the parent's rows (compact or generated) or are NULL by the NULL rule; primary-key
  and UNIQUE tuples are deduplicated before insert; a row that still fails a constraint is skipped and counted;
- generated child rows of a sum or lookup rule attach only to generated parent rows; D_c rows are never updated;
- the specification (tscore_gen/specification.json, written by the pipeline) is implemented by construction in the
  samplers: value pools and ranges, derived and dependent columns computed in Python from the sampled values held
  in memory (parent rows kept in memory for lookups and aggregates); the program never evaluates a rule, lookup or
  formula with SQL;
- NULL rule: NULL is a value to generate: for every nullable column (including nullable foreign keys), each instance contains
  generated rows with NULL and rows with non-NULL values, with a NULL share following the compact database's share
  for that column and at least one NULL row per nullable column; NOT NULL / primary-key columns never get NULL;
  rules, lookups and formulas constrain only non-NULL operands (SQL three-valued logic: a rule holds when its
  expression is not FALSE), and a planted NULL is never replaced to satisfy a rule.
- rows are written with executemany inside one transaction; the instance connection sets PRAGMA
  journal_mode=MEMORY, synchronous=OFF, temp_store=MEMORY; target 0.1 s per instance;
- the last stdout line is JSON {"db", "n_ok", "n_fail", "wall_s", "pool_sqls", "pool_skipped", "pool_values",
  "errors", "rows_added", "rows_skipped"} (rows_added and rows_skipped per table, summed over the instances).
"""


def plain_pool(pool_path, workdir):
    """Path of a plain JSON pool (a ``.json.gz`` pool is decompressed into ``workdir``)."""
    pool_path = Path(pool_path)
    if pool_path.suffix != '.gz':
        return pool_path
    target = Path(workdir) / pool_path.stem
    with gzip.open(pool_path, 'rb') as source, open(target, 'wb') as out:
        shutil.copyfileobj(source, out)
    return target


DIAG_HOOK = Path(__file__).resolve().parent / 'diag_hook'


def run_program(program_dir, ds, db, compact, pool, root, n_units, procs=1, tag='dc', timeout=3600, diag_file=None):
    """Run ``program_dir/tscore_gen``; returns (return code, stdout, stderr, instance paths)."""
    command = [sys.executable, '-m', 'tscore_gen.cli', 'generate', '--db', db, '--orig', str(compact), '--ds', ds,
               '--root', str(root), '--pool-sqls', str(pool), '--i0', '0', '--i1', str(n_units),
               '--seed-base', '42', '--procs', str(procs), '--tag', tag]
    env = dict(os.environ, PYTHONPATH=str(program_dir), PYTHONHASHSEED='0', OMP_NUM_THREADS='1',
               PYTHONDONTWRITEBYTECODE='1')
    if diag_file:
        env.update(PYTHONPATH=os.pathsep.join([str(program_dir), str(DIAG_HOOK)]), COREDB_DIAG_FILE=str(diag_file),
                   COREDB_DIAG_ROOT=str(Path(program_dir) / 'tscore_gen'))
    try:
        run = subprocess.run(command, capture_output=True, text=True, cwd=program_dir, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return -1, '', 'timeout', []
    units = sorted(str(p) for p in Path(root).glob('%s/%s__%s_*/*.sqlite' % (ds, db, tag)))
    return run.returncode, run.stdout, run.stderr, units


def drop_compact_copies(units, compact):
    """(instances, dropped count): an instance byte-identical to the compact database adds no row; a unit that fails
    after copying the compact database leaves such a file."""
    base = sha_file(compact)
    kept = [u for u in units if sha_file(u) != base]
    return kept, len(units) - len(kept)


def generate(ds, db, compact, program_dir, out_dir, n_units, procs):
    """Generate ``n_units`` instances into ``out_dir/units``; returns the generation record."""
    program_dir, out_dir = Path(program_dir).resolve(), Path(out_dir).resolve()
    pool = next(program_dir.glob('pool_sqls.json*'), None)
    if pool is None:
        raise FileNotFoundError('no pool_sqls.json(.gz) in %s' % program_dir)
    start = time.time()
    with tempfile.TemporaryDirectory() as workdir:
        code, stdout, stderr, units = run_program(program_dir, ds, db, compact, plain_pool(pool, workdir),
                                                  out_dir / 'units', n_units, procs)
    lines = stdout.strip().splitlines()
    units, copies = drop_compact_copies(units, compact)
    try:
        summary = json.loads(lines[-1]) if code == 0 and lines else None
    except ValueError:
        summary = None
    from .checks import instance_validity
    entries, validity = instance_validity(units, compact, program_instances=(summary or {}).get('instances')
                                          if isinstance(summary, dict) else None)
    return {'ds': ds, 'db': db, 'returncode': code, 'wall_s': round(time.time() - start, 1),
            'summary': summary, 'stderr_tail': stderr[-1500:],
            'units': units, 'compact_copies_dropped': copies, 'compact_sha256': sha_file(compact),
            'program': str(program_dir), 'validity': validity,
            'valid_units': [u for u, e in zip(units, entries) if e['valid']],
            'invalid_units': [u for u, e in zip(units, entries) if not e['valid']], 'instances': entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ds', required=True, choices=['bird', 'spider'])
    parser.add_argument('--db', required=True)
    parser.add_argument('--compact', required=True, help='compact SQLite database (step 1)')
    parser.add_argument('--program', help='directory with tscore_gen/ and pool_sqls.json[.gz] '
                                          '(default: value_filling_by_agents/<ds>/<db>)')
    parser.add_argument('--out', required=True, help='output directory of this database')
    parser.add_argument('--n-units', type=int, default=200)
    parser.add_argument('--procs', type=int, default=4)
    args = parser.parse_args()
    program = args.program or RELEASED / args.ds / args.db
    record = generate(args.ds, args.db, Path(args.compact).resolve(), program, args.out, args.n_units, args.procs)
    save_json(Path(args.out) / 'generation.json', record)
    print(args.db, record['returncode'], len(record['units']), 'valid', record['validity']['valid'], record['wall_s'])


if __name__ == '__main__':
    main()
