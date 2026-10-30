"""Sample candidate database instances with a generation program (package ``tscore_gen``, no LLM call).

Program interface (also given to the Engineer):
  python -m tscore_gen.cli generate --db <db_id> --orig <compact.sqlite> --ds <bird|spider> --root <out_root>
      --pool-sqls <pool_sqls.json> --i0 0 --i1 <N> --seed-base 42 --procs <P> --tag <tag>
- pure Python (standard library + sqlparse), no LLM or network call; the compact database is only read;
- instance i is written atomically to <root>/<ds>/<db>__<tag>_%04d/<db>__<tag>_%04d.sqlite with only
  random.Random(seed_base * 100003 + i), so the same seed gives the same file; instances keep the schema and keys;
- --pool-sqls is a JSON list of construction SQL whose literals are an extra value pool;
- the last stdout line is JSON {"db", "n_ok", "n_fail", "wall_s", "pool_sqls", "pool_skipped", "pool_values", "errors"}.
"""
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


def plain_pool(pool_path, workdir):
    """Path of a plain JSON pool (a ``.json.gz`` pool is decompressed into ``workdir``)."""
    pool_path = Path(pool_path)
    if pool_path.suffix != '.gz':
        return pool_path
    target = Path(workdir) / pool_path.stem
    with gzip.open(pool_path, 'rb') as source, open(target, 'wb') as out:
        shutil.copyfileobj(source, out)
    return target


def run_program(program_dir, ds, db, compact, pool, root, n_units, procs=1, tag='dc', timeout=3600):
    """Run ``program_dir/tscore_gen``; returns (return code, stdout, stderr, instance paths)."""
    command = [sys.executable, '-m', 'tscore_gen.cli', 'generate', '--db', db, '--orig', str(compact), '--ds', ds,
               '--root', str(root), '--pool-sqls', str(pool), '--i0', '0', '--i1', str(n_units),
               '--seed-base', '42', '--procs', str(procs), '--tag', tag]
    env = dict(os.environ, PYTHONPATH=str(program_dir), PYTHONHASHSEED='0', OMP_NUM_THREADS='1',
               PYTHONDONTWRITEBYTECODE='1')
    try:
        run = subprocess.run(command, capture_output=True, text=True, cwd=program_dir, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return -1, '', 'timeout', []
    units = sorted(str(p) for p in Path(root).glob('%s/%s__%s_*/*.sqlite' % (ds, db, tag)))
    return run.returncode, run.stdout, run.stderr, units


def generate(ds, db, compact, program_dir, out_dir, n_units, procs):
    """Generate ``n_units`` instances into ``out_dir/units``; returns the generation record."""
    program_dir, out_dir = Path(program_dir).resolve(), Path(out_dir).resolve()
    pool = next(program_dir.glob('pool_sqls.json*'), None)
    if pool is None:
        raise FileNotFoundError('no pool_sqls.json(.gz) in %s (pools over 1 MB are on HF thanhdath/core-db, '
                                'agentic_repo/pools/)' % program_dir)
    start = time.time()
    with tempfile.TemporaryDirectory() as workdir:
        code, stdout, stderr, units = run_program(program_dir, ds, db, compact, plain_pool(pool, workdir),
                                                  out_dir / 'units', n_units, procs)
    lines = stdout.strip().splitlines()
    return {'ds': ds, 'db': db, 'returncode': code, 'wall_s': round(time.time() - start, 1),
            'summary': json.loads(lines[-1]) if code == 0 and lines else None, 'stderr_tail': stderr[-1500:],
            'units': units, 'compact_sha256': sha_file(compact), 'program': str(program_dir)}


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
    print(args.db, record['returncode'], len(record['units']), record['wall_s'])


if __name__ == '__main__':
    main()
