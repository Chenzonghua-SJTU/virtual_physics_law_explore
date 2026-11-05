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
from types import MappingProxyType

MAX_LOG = 16000
MAX_RESULT = 2 * 1024 * 1024
MAX_ARTIFACTS = 8 * 1024 * 1024

ID_FIELDS = ('validation_id', 'residual_id', 'execution_id', 'observation_id', 'probe_id', 'law_id')


def record_id(record):
    return next((record[k] for k in ID_FIELDS if k in record), None) if isinstance(record, dict) else None


def get_record(inputs, alias, rid):
    if alias not in inputs:
        raise KeyError(f'Unknown input alias {alias!r}; available aliases: {list(inputs)}')
    records = inputs[alias]
    if not isinstance(records, list):
        raise ValueError(f'Input {alias!r} is not a record list')
    matches = [r for r in records if record_id(r) == rid]
    if len(matches) != 1:
        raise KeyError(f'Expected one record {rid!r} in {alias!r}; available IDs: {[record_id(r) for r in records]}')
    return matches[0]


def file_readers(encoded):
    """Read-only virtual files supplied by the host's acquired-file registry."""
    import re
    if not isinstance(encoded, dict) or len(encoded) > 128:
        raise ValueError('Invalid input file snapshot')
    decoded = {}
    for path, value in encoded.items():
        if (not isinstance(path, str) or not path or len(path) > 300
                or any(p in ('', '.', '..') or not re.fullmatch(r'[A-Za-z0-9_.-]+', p) for p in path.split('/'))):
            raise ValueError('Invalid snapshot path')
        decoded[path] = base64.b64decode(value, validate=True)
    files = MappingProxyType(decoded)
    def read_bytes(path):
        if path not in files:
            raise ValueError(f'File not included in this execution: {path!r}; available_files={list(files)}')
        return files[path]
    def read_file(path):
        return read_bytes(path).decode('utf-8')
    def read_json(path):
        # Parsing afresh keeps mutations local to the caller, never the snapshot.
        return json.loads(read_file(path))
    return {'available_files': tuple(sorted(files)), 'read_file': read_file,
            'read_json': read_json, 'read_bytes': read_bytes}


def probe_arrays(record, time_axis='observed', interpolation='exact'):
    """Only reformat acquired values; time alignment is explicit, never extrapolated."""
    import numpy as np
    if time_axis not in ('observed', 'acceleration') or interpolation not in ('exact', 'linear'):
        raise ValueError('time_axis must be observed/acceleration; interpolation must be exact/linear')
    def array(key, shape):
        if key not in record:
            raise ValueError(f'Missing probe field {key!r}; available fields: {list(record)}')
        a = np.array(record[key], dtype=float, copy=True)
        if a.shape != shape or not np.isfinite(a).all():
            raise ValueError(f'{key}: expected finite shape {shape}, got {a.shape}; no truncation is performed')
        return a
    raw_t = record.get('times')
    if not isinstance(raw_t, list) or not raw_t:
        raise ValueError('times must be a nonempty list')
    t = array('times', (len(raw_t),))
    if np.any(np.diff(t) <= 0):
        raise ValueError('times must be strictly increasing')
    r, v = array('r_obs', (len(t), 2)), array('v_obs', (len(t), 2))
    result = {'t': t, 'r': r, 'v': v, 'time_axis': time_axis, 'alignment': 'observed'}
    if time_axis == 'observed':
        return result
    raw_a_t = record.get('a_est_times')
    if not isinstance(raw_a_t, list) or not raw_a_t:
        raise ValueError('No estimated acceleration samples: a_est_times is missing or empty')
    at = array('a_est_times', (len(raw_a_t),))
    a = array('a_est', (len(at), 2))
    if np.any(np.diff(at) <= 0) or at[0] < t[0] or at[-1] > t[-1]:
        raise ValueError('a_est_times must increase within observed times; no extrapolation')
    idx = np.searchsorted(t, at)
    if interpolation == 'exact':
        if np.any(idx >= len(t)) or not np.array_equal(t[idx], at):
            raise ValueError('Acceleration times do not exactly match observed times; request interpolation="linear" explicitly if appropriate')
        rr, vv = r[idx].copy(), v[idx].copy()
    else:
        rr = np.column_stack([np.interp(at, t, r[:, j]) for j in range(2)])
        vv = np.column_stack([np.interp(at, t, v[:, j]) for j in range(2)])
    return {'t': at, 'r': rr, 'v': vv, 'a': a, 'time_axis': time_axis,
            'alignment': interpolation, 'acceleration_source': 'a_est (finite-difference estimate, not true acceleration)'}


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
                        'record_ids': [record_id(r) for r in records] if isinstance(records, list) else [],
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
                         'inputs': envelope['inputs'], 'input_info': input_layout(envelope['inputs']),
                         'get_record': lambda alias, rid: get_record(envelope['inputs'], alias, rid),
                         'probe_arrays': probe_arrays}
            namespace.update(file_readers(envelope.get('files', {})))
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
