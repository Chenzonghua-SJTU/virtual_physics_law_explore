"""One autonomous discovery session per OS process; key arrives over stdin only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .web_jobs import _now, _read, _write, accepted_submission


def run(directory):
    directory = Path(directory)
    environment = client = None
    try:
        # The server bounds the field; bound the local protocol as defense in depth.
        envelope = json.loads(sys.stdin.readline(8192))
        key = envelope.pop('api_key', None)
        if not isinstance(key, str) or not key:
            _write(directory / 'result.json', {'status': 'incomplete', 'reason': 'missing_api_key', 'submission': None})
            return 2
        os.environ['DEEPSEEK_API_KEY'] = key
        del key, envelope
        config = _read(directory / 'config.json', directory)
        from .agent import Agent
        from .environment import Environment
        from .model import DeepSeekClient
        from .runtime import ToolRuntime
        from .store import append_event
        environment = Environment(config['environment'])
        runtime = ToolRuntime(environment, directory, config=config.get('numerics'))
        mission = runtime.mission()
        _metadata(directory, session_started_at=_now(), initial_budget=mission.get('budget') or {})
        append_event(directory / 'events.jsonl', {'event': 'session_started', 'budget': mission.get('budget')})
        client = DeepSeekClient(config['model'], directory,
                                remaining_seconds=lambda: runtime.budget()['wall_seconds_remaining'])
        result = Agent(client, runtime, directory, config.get('agent', {})).run()
        client.close()
        client = None
        environment.close()
        environment = None
        os.environ.pop('DEEPSEEK_API_KEY', None)
        # The main Agent has returned and its simulator has closed. Only now may
        # a separate, key-free evaluator access hidden initial conditions.
        if result.get('status') == 'submitted' and accepted_submission(directory):
            _metadata(directory, status='evaluating')
            project = Path(__file__).resolve().parents[1]
            evaluation = subprocess.run([sys.executable, str(project / 'evaluate.py'), '--run-dir', str(directory)],
                                        cwd=project, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, timeout=180)
            _metadata(directory, evaluation_status='complete' if evaluation.returncode == 0 else 'failed')
        _metadata(directory, status=result.get('status', 'incomplete'), finished_at=_now())
        return 0
    except Exception:
        # No raw exception/traceback can disclose request headers or credentials.
        if not accepted_submission(directory):
            _write(directory / 'result.json', {'status': 'error', 'reason': 'worker_failed', 'submission': None})
            _metadata(directory, status='error', finished_at=_now())
        else:
            _metadata(directory, status='submitted', evaluation_status='failed', finished_at=_now())
        return 1
    finally:
        os.environ.pop('DEEPSEEK_API_KEY', None)
        for resource in (client, environment):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass


def _metadata(directory, **updates):
    value = _read(directory / 'web.json', directory, {})
    value.update(updates)
    _write(directory / 'web.json', value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True)
    args = parser.parse_args()
    raise SystemExit(run(Path(args.run_dir)))


if __name__ == '__main__':
    main()
