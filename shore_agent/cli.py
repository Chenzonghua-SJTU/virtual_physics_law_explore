"""Human entry point. No extra model-facing tools."""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from .environment import Environment
from .runtime import ToolRuntime
from shore_worlds import DEFAULT_WORLD_ID, WORLD_IDS, validate_world_id


def main():
    parser = argparse.ArgumentParser(description='Local physical-law discovery prototype')
    parser.add_argument('command', choices=['run', 'inspect', 'init'])
    parser.add_argument('--config', default='config.example.json')
    parser.add_argument('--run-dir')
    parser.add_argument('--noise', action='store_true')
    parser.add_argument('--world', choices=WORLD_IDS, help='World to explore; defaults to the configured world or world_1')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    if args.world is not None:
        config.setdefault('environment', {})['world_id'] = args.world
    try:
        validate_world_id(config.get('environment', {}).get('world_id', DEFAULT_WORLD_ID))
    except ValueError:
        parser.error('Unknown environment.world_id; choose ' + ', '.join(WORLD_IDS))
    if args.noise:
        config['environment']['noise'] = True
    if args.command == 'inspect':
        if not args.run_dir:
            parser.error('inspect requires --run-dir')
        directory = Path(args.run_dir)
        for name in ('result.json', 'evaluation.json'):
            if (directory / name).exists():
                print((directory / name).read_text(encoding='utf-8'))
        print('Records:', {p.name: len(list(p.glob('*.json'))) for p in (directory / 'records').glob('*') if p.is_dir()})
        return
    directory = Path(args.run_dir or ('runs/live-' + datetime.now().strftime('%Y%m%d-%H%M%S')))
    if directory.exists() and any(directory.iterdir()):
        parser.error('Use a new empty run directory; sessions cannot silently reset or resume')
    directory.mkdir(parents=True, exist_ok=True)
    # Persist the effective settings even when starting from an older config.
    config.setdefault('model', {}).update(max_calls=None, main_max_calls=None)
    config.setdefault('agent', {}).pop('max_turns', None)
    config['agent'].pop('max_rounds', None)
    (directory / 'config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    env = Environment(config['environment'])
    try:
        runtime = ToolRuntime(env, directory, config=config.get('numerics'))
        mission = runtime.mission()
        if not mission['ok']:
            raise RuntimeError(mission['error'])
        if args.command == 'init':
            print(json.dumps(mission, ensure_ascii=False, indent=2))
            result = {'status': 'initialized_only', 'reason': 'No model called; first-light records saved.'}
        elif not os.environ.get('DEEPSEEK_API_KEY'):
            result = {'status': 'incomplete', 'reason': 'DEEPSEEK_API_KEY is absent; real API run not verified.',
                      'real_api_attempted': False, 'submission': None}
            print(result['reason'])
        else:
            from .model import DeepSeekClient
            from .agent import Agent
            client = DeepSeekClient(config['model'], directory,
                                    remaining_seconds=lambda: runtime.budget()['wall_seconds_remaining'])
            try:
                result = Agent(client, runtime, directory, config.get('agent', {})).run()
            finally:
                client.close()
        (directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Run directory:', directory.resolve())
    finally:
        env.close()


if __name__ == '__main__':
    main()
