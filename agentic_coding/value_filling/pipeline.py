"""Agentic coding for value filling: Designer -> Engineer -> checks -> Reviewer, until the Reviewer passes.

The Engineer starts from a released generation program and edits package ``tscore_gen``.  Output in ``--out``:
``tscore_gen/`` (reviewed program), ``plan.json`` (specification and reviews), ``record.json`` (final checks,
rounds, LLM spend), ``pool_sqls.json`` (construction SQL, the literal pool) and ``llm_calls/`` (one log per call).
"""
import argparse
import json
import shutil
from pathlib import Path

from ..common import load_json, save_json
from . import generate, prompts
from .agent_inputs import agent_inputs
from .checks import construction_feedback
from .llm_client import DEFAULT_BASE_URL, ChatClient, parse_files, parse_json_block

DEFAULT_MODEL = 'deepseek/deepseek-v4.1-flash-1017'
DEFAULT_TEMPLATE = generate.RELEASED / 'spider' / 'allergy_1' / 'tscore_gen'
SYSTEM = {'designer': 'You are a careful database designer.', 'engineer': 'You are a careful Python engineer.',
          'reviewer': 'You are an independent reviewer.'}


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


class ValueFillingPipeline:
    """Designer / Engineer / Reviewer loop for one database."""

    def __init__(self, args):
        self.args = args
        self.out = Path(args.out)
        self.package = self.out / 'tscore_gen'
        self.pool = self.out / 'pool_sqls.json'
        self.client = ChatClient(self.out / 'llm_calls', args.budget_usd, args.base_url)
        self.pairs = load_json(args.pairs)['pairs']
        self.inputs = agent_inputs(args.compact, self.pairs)

    def prepare(self):
        """Fresh output directory with the template program and the literal pool."""
        self.out.mkdir(parents=True, exist_ok=True)
        if self.package.exists():
            shutil.rmtree(self.package)
        shutil.copytree(self.args.template, self.package, ignore=shutil.ignore_patterns('__pycache__'))
        sqls = sorted({p['gold_sql'] for p in self.pairs} | {p['neighbor_sql'] for p in self.pairs})
        self.pool.write_text(json.dumps(sqls))

    def ask(self, role, prompt, max_tokens=16000):
        """One agent call; returns the response text."""
        return self.client.chat(role, self.args.model, SYSTEM[role], prompt, max_tokens=max_tokens)

    def design(self, review):
        """Designer call: returns the generation specification (dict, possibly empty)."""
        prompt = prompts.DESIGNER.format(review_report=json.dumps(review or {}), **self.inputs)
        return parse_json_block(self.ask('designer', prompt)) or {}

    def engineer(self, specification, review):
        """Engineer call: writes the returned files into the package."""
        prompt = prompts.ENGINEER.format(generation_specification=json.dumps(specification),
                                         program_interface=generate.__doc__,
                                         previous_program=program_source(self.package),
                                         review_report=json.dumps(review or {}), **self.inputs)
        return apply_files(self.package, parse_files(self.ask('engineer', prompt, max_tokens=32000)))

    def review(self, specification, feedback):
        """Reviewer call: returns the review report (dict)."""
        prompt = prompts.REVIEWER.format(generation_specification=json.dumps(specification),
                                         generation_program=program_source(self.package),
                                         execution_feedback=json.dumps(feedback, indent=1), **self.inputs)
        report = parse_json_block(self.ask('reviewer', prompt))
        return report or {'recommendation': 'revise', 'issues': [], 'note': 'unparseable report'}

    def check(self):
        """Automated checks of the current program on the compact database."""
        return construction_feedback(self.out, self.args.db, self.args.ds, self.args.original, self.args.compact,
                                     self.pool, self.pairs, n_units=self.args.check_units)

    def run(self):
        """Run up to ``max_rounds`` design/implement/review rounds; returns the final record."""
        self.prepare()
        specification, review, history = {}, None, []
        for round_index in range(1, self.args.max_rounds + 1):
            if round_index == 1 or issues_for(review, 'designer'):
                specification = self.design(review)
            changed = self.engineer(specification, review)
            feedback = self.check()
            review = self.review(specification, feedback)
            history.append({'round': round_index, 'changed_files': changed, 'checks': feedback, 'review': review})
            if review.get('recommendation') == 'pass':
                break
        save_json(self.out / 'plan.json', {'db': self.args.db, 'generation_specification': specification,
                                           'reviews': [h['review'] for h in history]})
        record = {'db': self.args.db, 'benchmark': self.args.ds, 'rounds': len(history),
                  'status': 'pass' if review and review.get('recommendation') == 'pass' else 'not_passed',
                  'final_checks': history[-1]['checks'] if history else None, 'model': self.args.model,
                  'llm_calls': self.client.calls, 'cost_usd': round(self.client.spent_usd, 4),
                  'history': [{k: h[k] for k in ('round', 'changed_files')} for h in history]}
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
    parser.add_argument('--template', default=str(DEFAULT_TEMPLATE), help='starting program package')
    parser.add_argument('--model', default=DEFAULT_MODEL, help='model of the three agents')
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL, help='OpenAI-compatible endpoint')
    parser.add_argument('--budget-usd', type=float, default=5.0, help='LLM spend cap of this run')
    parser.add_argument('--max-rounds', type=int, default=4)
    parser.add_argument('--check-units', type=int, default=20)
    record = ValueFillingPipeline(parser.parse_args()).run()
    print(json.dumps({k: record[k] for k in ('db', 'status', 'rounds', 'llm_calls', 'cost_usd')}))


if __name__ == '__main__':
    main()
