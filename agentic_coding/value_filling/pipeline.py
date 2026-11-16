"""Agentic coding for value filling: Designer -> Engineer -> checks -> Reviewer, until the Reviewer passes."""
import argparse
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

from ..common import load_json, save_json
from ..separation import eligible_pairs
from . import generate, prompts
from .agent_inputs import agent_inputs
from .checks import construction_feedback
from .llm_client import DEFAULT_BASE_URL, BudgetExceeded, ChatClient, parse_files, parse_json_block

DEFAULT_MODEL = 'deepseek/deepseek-v4.1-flash-1017'
BASE_PROGRAM = Path(__file__).resolve().parent / 'base_program'
SYSTEM = {'designer': 'You are a careful database designer.', 'engineer': 'You are a careful Python engineer.',
          'reviewer': 'You are an independent reviewer.'}
DESIGNER_LIMIT = 131072
SIZE_RETRY = ('Your previous specification was not accepted: the previous reply exceeded the size limit; keep the '
              'specification under 60,000 characters. Answer the same task again with one JSON object '
              'that has exactly the keys generic_sampling_rules, per_column_exceptions (a list of at most 30 entries), '
              'dependencies, semantic_rules_and_formulas (a list of {"table", "column", "formula"} rows), '
              'table_sizes_per_instance, supporting_evidence and uncertainty, in at most 60,000 characters.\n\n')
ENGINEER_GROUP_CHARS = 100000
ENGINEER_PROMPT_CHARS = 180000


def program_source(package_dir):
    """All files of a program package, rendered in the Engineer output format."""
    return '\n\n'.join('### FILE: tscore_gen/%s\n```python\n%s```' % (path.name, path.read_text())
                       for path in sorted(Path(package_dir).glob('*.py')))


def apply_files(package_dir, files):
    """Write the Engineer's files into the package; returns the changed file names."""
    changed = []
    for relative, content in files.items():
        target = Path(package_dir) / Path(relative).name
        target.write_text(content if content.endswith('\n') else content + '\n')
        changed.append(target.name)
    return changed


def issues_for(report, agent):
    """Issues of a review report addressed to one agent."""
    issues = (report or {}).get('issues', [])
    return [i for i in issues if str(i.get('agent', i.get('responsible', ''))).lower() == agent]


def fit_inputs(build, inputs, limit, order):
    """Cut the fields of ``inputs`` in ``order`` ((field, characters always kept) pairs; each cut from its end to
    what still fits) until ``build(inputs)`` has at most ``limit`` characters; returns the prompt."""
    inputs, original = dict(inputs), {field: len(text) for field, text in inputs.items()}
    prompt = build(inputs)
    for field, floor in order:
        excess = len(prompt) - limit
        if excess <= 0:
            break
        text = inputs[field].split('\n... (cut at ')[0]
        keep = max(floor, len(text) - excess - 200)
        if keep < len(text):
            inputs[field] = text[:keep] + '\n... (cut at %d of %d characters to keep the prompt short)' % (
                keep, original[field])
            prompt = build(inputs)
    return prompt


def round_line(history_entry):
    """One earlier round's check result for the Reviewer (exit code, instances, valid, units failed)."""
    checks = history_entry['checks']
    try:
        summary = json.loads(checks.get('summary') or '{}')
    except (ValueError, TypeError):
        summary = {}
    return {'round': history_entry['round'], 'returncode': checks.get('returncode'),
            'instances': checks.get('n_instances'), 'valid': (checks.get('validity') or {}).get('valid'),
            'units_failed': summary.get('n_fail') if isinstance(summary, dict) else None,
            'recommendation': (history_entry.get('review') or {}).get('recommendation')}


class ValueFillingPipeline:
    """Designer / Engineer / Reviewer loop for one database."""

    def __init__(self, args):
        self.args = args
        self.out = Path(args.out)
        self.package = self.out / 'tscore_gen'
        self.pool = self.out / 'pool_sqls.json'
        self.client = ChatClient(self.out / 'llm_calls', args.budget_usd, args.base_url, args.call_timeout_s)
        self.pairs = load_json(args.pairs)['pairs']
        self.eligible = eligible_pairs(args.original, self.pairs)
        self.inputs = agent_inputs(args.original, args.compact, self.eligible)
        self.limit = min(393216, self.client.max_completion_tokens(args.model) or 128000)
        self.engineer_cost = 0.0
        self.started = time.time()

    def prepare(self):
        """Fresh output directory with the generic program and the literal pool."""
        self.out.mkdir(parents=True, exist_ok=True)
        if self.package.exists():
            shutil.rmtree(self.package)
        self.package.mkdir()
        for path in sorted(BASE_PROGRAM.glob('*.py')):
            shutil.copyfile(path, self.package / path.name)
        sqls = sorted({p['gold_sql'] for p in self.pairs} | {p['neighbor_sql'] for p in self.pairs})
        self.pool.write_text(json.dumps(sqls))

    def ask(self, role, prompt, max_tokens, reserve=0.0):
        """One agent call; returns the response text."""
        if time.time() - self.started > self.args.max_wall_s:
            raise BudgetExceeded('run wall limit of %d s reached' % self.args.max_wall_s)
        return self.client.chat(role, self.args.model, SYSTEM[role], prompt, max_tokens=max_tokens, reserve=reserve)

    def view(self, role):
        """Agent inputs of the Engineer or the Reviewer: the Designer's per-column atomic-operation summary, for the
        Engineer followed by the full group list (at most ENGINEER_GROUP_CHARS characters of it); the Reviewer
        gets no column values or statistics."""
        inputs = dict(self.inputs, atomic_operations=self.inputs['atomic_operations_designer'])
        if role == 'engineer':
            groups = self.inputs['atomic_operations']
            if len(groups) > ENGINEER_GROUP_CHARS:
                groups = groups[:ENGINEER_GROUP_CHARS] + '\n... (list cut at %d of %d characters)' % (
                    ENGINEER_GROUP_CHARS, len(groups))
            inputs['atomic_operations'] += '\n\nFull atomic-operation group list:\n' + groups
        else:
            inputs.update(column_values='(fast mode: see the specification)',
                          column_statistics='(fast mode: see the specification and the execution feedback)')
        return inputs

    def design(self, review, previous):
        """Designer call: returns the generation specification, also written to tscore_gen/specification.json (the
        program loads it); None when the reply has no JSON object."""
        inputs = dict(self.inputs, atomic_operations=self.inputs['atomic_operations_designer'])
        prompt = prompts.DESIGNER.format(previous_specification=json.dumps(previous or {}),
                                         review_report=json.dumps(review or {}), **inputs)
        text = self.ask('designer', prompt, DESIGNER_LIMIT)
        if self.client.last_finish_reason == 'length':
            text = self.ask('designer', SIZE_RETRY + prompt, DESIGNER_LIMIT)
            if self.client.last_finish_reason == 'length':
                return None
        specification = parse_json_block(text)
        if specification:
            (self.package / 'specification.json').write_text(json.dumps(specification, indent=1))
        return specification or None

    def engineer(self, specification, review):
        """Engineer call: writes the returned files into the package."""
        def build(inputs):
            return prompts.ENGINEER.format(generation_specification=json.dumps(specification),
                                           program_interface=generate.PROGRAM_INTERFACE,
                                           previous_program=program_source(self.package),
                                           review_report=json.dumps(review or {}), **inputs)
        order = (('atomic_operations', len(self.inputs['atomic_operations_designer'])), ('column_statistics', 0),
                 ('column_values', 0), ('atomic_operations', 0))
        prompt = fit_inputs(build, self.view('engineer'), ENGINEER_PROMPT_CHARS, order)
        text = self.ask('engineer', prompt, self.limit, reserve=2.4 * self.engineer_cost)
        self.engineer_cost = self.client.last_cost
        return apply_files(self.package, parse_files(text))

    def review(self, specification, feedback):
        """Reviewer call: returns the review report (dict)."""
        feedback = dict(feedback, stderr_tail=feedback['stderr_tail'][-1500:])
        prompt = prompts.REVIEWER.format(generation_specification=json.dumps(specification),
                                         generation_program=program_source(self.package),
                                         execution_feedback=json.dumps(feedback, indent=1), **self.view('reviewer'))
        report = parse_json_block(self.ask('reviewer', prompt, self.limit))
        return report or {'recommendation': 'revise', 'issues': [], 'note': 'unparseable report'}

    def check(self):
        """Automated checks of the current program on the compact database."""
        return construction_feedback(self.out, self.args.db, self.args.ds, self.args.original, self.args.compact,
                                     self.pool, self.pairs, n_units=self.args.check_units,
                                     procs=min(8, len(os.sched_getaffinity(0))), eligible=self.eligible)

    def snapshot(self, round_index):
        """Keep a copy of the package after one round (rounds/r<k>/tscore_gen)."""
        target = self.out / 'rounds' / ('r%d' % round_index) / 'tscore_gen'
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(self.package, target, ignore=shutil.ignore_patterns('__pycache__'))

    def restore(self, round_index):
        """Make the package of one round the final package."""
        shutil.rmtree(self.package)
        shutil.copytree(self.out / 'rounds' / ('r%d' % round_index) / 'tscore_gen', self.package)

    def run(self):
        """Run up to ``max_rounds`` design/implement/review rounds; returns the final record."""
        self.prepare()
        specification, review, history, stopped = {}, None, [], 'max_rounds_reached'
        try:
            for round_index in range(1, self.args.max_rounds + 1):
                if round_index == 1 or issues_for(review, 'designer'):
                    specification = self.design(review, specification) or specification
                changed = self.engineer(specification, review)
                feedback = self.check()
                feedback['previous_rounds'] = [round_line(h) for h in history]
                self.snapshot(round_index)
                review = self.review(specification, feedback)
                history.append({'round': round_index, 'changed_files': changed, 'checks': feedback,
                                'specification': specification, 'review': review})
                if review.get('recommendation') == 'pass':
                    stopped = 'reviewer_pass'
                    break
        except BudgetExceeded as exc:
            stopped = 'limit: %s' % exc
        except Exception as exc:
            stopped = 'exception: %s: %s' % (type(exc).__name__, str(exc)[:300])
            traceback.print_exc()
        valid = [h for h in history if (h['checks'].get('validity') or {}).get('valid')]
        passed = [h for h in valid if h['review'].get('recommendation') == 'pass']
        best = (passed or valid or [None])[-1]
        if best:
            self.restore(best['round'])
            specification = best['specification']
        save_json(self.out / 'plan.json', {'db': self.args.db, 'shipped_round': best and best['round'],
                                           'generation_specification': specification,
                                           'reviews': [h['review'] for h in history]})
        record = {'db': self.args.db, 'benchmark': self.args.ds, 'rounds': len(history),
                  'status': 'pass' if review and review.get('recommendation') == 'pass' else 'not_passed',
                  'stopped': stopped, 'shipped_round': best and best['round'],
                  'final_checks': best and best['checks'], 'model': self.args.model,
                  'llm_calls': self.client.calls, 'cost_usd': round(self.client.spent_usd, 4),
                  'history': [{'round': h['round'], 'changed_files': h['changed_files'],
                               'valid': (h['checks'].get('validity') or {}).get('valid'),
                               'recommendation': h['review'].get('recommendation')} for h in history]}
        save_json(self.out / 'record.json', record)
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ds', required=True, choices=['bird', 'spider'])
    parser.add_argument('--db', required=True)
    parser.add_argument('--original', required=True, help='original SQLite database (eligibility of pairs)')
    parser.add_argument('--compact', required=True, help='compact SQLite database (step 1)')
    parser.add_argument('--pairs', required=True, help='pairs.json (step 2)')
    parser.add_argument('--out', required=True)
    parser.add_argument('--model', default=DEFAULT_MODEL, help='model of the three agents')
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL, help='OpenAI-compatible endpoint')
    parser.add_argument('--budget-usd', type=float, default=0.2, help='LLM spend cap of this run')
    parser.add_argument('--max-wall-s', type=float, default=3600, help='no new LLM call after this many seconds')
    parser.add_argument('--call-timeout-s', type=float, default=240, help='wall limit of one LLM call')
    parser.add_argument('--max-rounds', type=int, default=4)
    parser.add_argument('--check-units', type=int, default=20)
    record = ValueFillingPipeline(parser.parse_args()).run()
    print(json.dumps({k: record[k] for k in ('db', 'status', 'rounds', 'llm_calls', 'cost_usd', 'stopped')}))
    if record['shipped_round'] is None or record['stopped'].startswith('exception'):
        sys.exit(1)


if __name__ == '__main__':
    main()
