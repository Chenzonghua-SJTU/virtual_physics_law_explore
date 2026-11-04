"""Container-only runner. No project, credentials, host mounts or scientific truth.

This process is NOT a Python sandbox. Docker enforces the security boundary.
User code and all output of this process are untrusted experimental artifacts.
"""
import base64
import contextlib
import io
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import time
import traceback

MAX_LOG = 16000
MAX_RESULT = 2 * 1024 * 1024
MAX_ARTIFACTS = 8 * 1024 * 1024


def json_value(value):
    """Convert scientific containers, never silently replace nonfinite values."""
    import numpy as np
    if isinstance(value, np.ndarray):
        return json_value(value.tolist())
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise TypeError('Result dictionary keys must be strings')
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('Nonfinite result (NaN/Infinity); inspect the calculation or explicitly mark missing values with None')
        return value
    raise TypeError(f'Unsupported result type: {type(value).__name__}; return numbers, strings, lists or dictionaries')


def input_layout(inputs):
    def describe(value):
        if isinstance(value, list):
            shape, current = [], value
            while isinstance(current, list):
                shape.append(len(current))
                current = current[0] if current else None
            return {'type': 'list', 'first_item_shape': shape}
        return {'type': type(value).__name__}
    layout = {}
    for name, records in inputs.items():
        first = records[0] if isinstance(records, list) and records else records
        layout[name] = {'count': len(records) if isinstance(records, list) else None,
                        'first_record_fields': {k: describe(v) for k, v in list(first.items())[:40]}
                        if isinstance(first, dict) else describe(first)}
    return layout


class BoundedLog(io.TextIOBase):
    def __init__(self):
        self.parts, self.size, self.truncated = [], 0, False

    def write(self, value):
        value = str(value)
        remaining = max(0, MAX_LOG - self.size)
        self.parts.append(value[:remaining]) if remaining else None
        self.size += min(len(value), remaining)
        self.truncated |= len(value) > remaining
        return len(value)

    def flush(self):
        pass

    def value(self):
        return ''.join(self.parts) + ('\n[output truncated]' if self.truncated else '')


def main():
    # An OS signal deadline also covers orphaned client/worker processes.
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.alarm(int(sys.argv[1]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_ARTIFACTS, MAX_ARTIFACTS))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    envelope = json.loads(sys.stdin.buffer.read(32 * 1024 * 1024))
    Path('/work/output').mkdir(exist_ok=True)
    os.environ.update(HOME='/work', MPLCONFIGDIR='/work/.matplotlib')
    stdout, stderr = BoundedLog(), BoundedLog()
    started = time.monotonic()
    result = None
    error = None
    status = 'success'
    warnings = []
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            namespace = {'__name__': '__analysis__', '__file__': '/work/analysis.py',
                         'inputs': envelope['inputs']}
            Path('/work/analysis.py').write_text(envelope['code'])
            exec(compile(envelope['code'], '/work/analysis.py', 'exec'), namespace)
            if 'result' in namespace:
                result = namespace['result']
            elif callable(namespace.get('analyze')):
                result = namespace['analyze'](envelope['inputs'])  # old scripts remain readable/runnable
            else:
                result = None
                warnings.append('No structured result was assigned. Any printed output is in stdout; use result = {...} to return reusable values.')
            result = json_value(result)
            encoded = json.dumps(result, allow_nan=False, ensure_ascii=False)
            if len(encoded.encode()) > MAX_RESULT:
                raise ValueError('result exceeds 2 MiB; save large tables in output/')
        except BaseException as exc:
            result = None
            status = 'error'
            frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename == '/work/analysis.py']
            line = frames[-1].lineno if frames else getattr(exc, 'lineno', None)
            source = envelope['code'].splitlines()
            error = {'type': type(exc).__name__, 'message': str(exc)[:2000],
                     'line': line, 'source_line': source[line-1][:500] if line and 0 < line <= len(source) else None,
                     'input_layout': input_layout(envelope['inputs']),
                     'traceback': traceback.format_exc()[-12000:]}
    artifacts, total = [], 0
    # Export only regular files with simple names, never symlinks or directories.
    for path in sorted(Path('/work/output').iterdir()):
        import re
        if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', path.name)
                or path.suffix not in ('.png', '.json', '.txt', '.csv')
                or not stat.S_ISREG(path.lstat().st_mode) or path.is_symlink()):
            continue
        size = path.stat().st_size
        if len(artifacts) >= 10 or total + size > MAX_ARTIFACTS:
            stderr.write('\nArtifact limit exceeded; additional files were not exported.')
            break
        content = path.read_bytes()
        total += len(content)
        artifacts.append({'name': path.name, 'base64': base64.b64encode(content).decode('ascii')})
    usage = resource.getrusage(resource.RUSAGE_SELF)
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    response = {'status': status, 'result': result, 'error': error, 'warnings': warnings, 'stdout': stdout.value(),
                'stderr': stderr.value(), 'artifacts': artifacts,
                'compute_seconds': time.monotonic() - started,
                'cpu_seconds_reported': usage.ru_utime + usage.ru_stime + child.ru_utime + child.ru_stime,
                'peak_rss_kib_reported': usage.ru_maxrss}
    sys.stdout.write(json.dumps(response, ensure_ascii=False, allow_nan=False))
    sys.stdout.flush()


if __name__ == '__main__':
    main()
