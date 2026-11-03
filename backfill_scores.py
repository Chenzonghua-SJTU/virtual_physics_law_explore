"""Add PDF-formula score sidecars to ended archives, without changing evidence.

No model requests, probe launches, fitting, or candidate re-evaluation occur.
Saved hidden initial conditions are used only to reconstruct the truth variance.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid

from evaluate import score_existing_evaluation


def _write(path, value):
    temp = path.with_name('.' + path.name + '-' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def backfill_scores(runs_dir, *, include_trash=False, skip_runs=()):
    roots = [Path(runs_dir)]
    if include_trash and not (roots[0] / '.trash').is_symlink():
        roots.append(roots[0] / '.trash')
    rows, cache = [], {}
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        for directory in sorted(root.iterdir()):
            if (not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', directory.name)
                    or directory.is_symlink() or not directory.is_dir() or directory.name in skip_runs):
                continue
            path = directory / 'evaluation.json'
            if not path.is_file() or path.is_symlink():
                continue
            row = {'run_id': directory.name, 'in_trash': root.name == '.trash'}
            try:
                original = path.read_bytes()
                evaluation = json.loads(original)
                if not isinstance(evaluation, dict):
                    raise ValueError('invalid_evaluation')
                digest = hashlib.sha256(original).hexdigest()
                if isinstance(evaluation.get('score'), dict):
                    score, source = evaluation['score'], 'embedded'
                else:
                    score = score_existing_evaluation(directory, evaluation, reference_cache=cache)
                    if path.read_bytes() != original:
                        rows.append(dict(row, status='skipped', reason='evaluation_changed_during_scoring'))
                        continue
                    target = directory / 'evaluation_score.json'
                    if target.is_symlink():
                        rows.append(dict(row, status='skipped', reason='score_path_is_symlink'))
                        continue
                    _write(target, {'evaluation_sha256': digest, 'score': score,
                                    'created_at': datetime.now(timezone.utc).isoformat(),
                                    'note': 'Original evaluation and exploration records were not modified.'})
                    source = 'sidecar'
                rows.append(dict(row, status=score.get('status'), reason=score.get('reason'),
                                 total=score.get('total'), prediction=score.get('prediction'),
                                 law=score.get('law'), conservation=score.get('conservation'),
                                 source=source, evaluation_sha256=digest))
            except (OSError, ValueError, TypeError, KeyError, OverflowError):
                rows.append(dict(row, status='unavailable', reason='archive_could_not_be_scored'))
    return {'formula_version': 'shore_pdf_1101', 'api_calls': 0,
            'original_evaluations_unchanged': True, 'reference_cache_entries': len(cache),
            'counts': dict(Counter(row['status'] for row in rows)), 'runs': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs-dir', default='runs')
    parser.add_argument('--include-trash', action='store_true')
    parser.add_argument('--skip-run', action='append', default=[])
    parser.add_argument('--output')
    args = parser.parse_args()
    result = backfill_scores(args.runs_dir, include_trash=args.include_trash, skip_runs=args.skip_run)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        _write(output, result)
    print(json.dumps({key: value for key, value in result.items() if key != 'runs'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
