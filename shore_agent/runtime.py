"""Seven scientific tools. Reads only acquired records, never simulator internals."""
import ast
import copy
import json
import time
import uuid
from pathlib import Path

import numpy as np
from jsonschema import validate
from .schemas import SCHEMAS, tool_schemas
from .store import Store, preview, append_event
from .observations import estimate_static_bodies, estimate_body_trajectories
from .expressions import Expression
from . import numerics


def correlation(a, b):
    if len(a) < 3:
        return {'value': None, 'reason': 'fewer than three samples'}
    if np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return {'value': None, 'reason': 'constant or numerically constant variable'}
    return {'value': float(np.corrcoef(a, b)[0, 1]), 'reason': None}


def statistics(a):
    a = np.asarray(a, dtype=float)
    if a.size == 0:
        return {'mean': None, 'rmse': None, 'max_abs': None, 'reason': 'no internal samples'}
    return {'mean': a.mean(axis=0).tolist(), 'rmse': np.sqrt((a*a).mean(axis=0)).tolist(),
            'max_abs': np.abs(a).max(axis=0).tolist()}


class ToolRuntime:
    schemas = SCHEMAS

    def __init__(self, environment, run_dir, config=None, code_config=None):
        self.environment = environment
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.run_dir / 'records')
        self.config = config or {}
        self.code_config = code_config or {}
        self.code_enabled = self.code_config.get('enabled', False)
        if type(self.code_enabled) is not bool:
            raise ValueError('code_execution.enabled must be boolean')
        self.schemas = tool_schemas(self.code_enabled)
        self.task = None
        self.known_bodies = []
        self.body_position_estimate = None
        self._initial_mission = None
        self.session_ended = False

    def budget(self):
        response = self.environment.request('budget')
        if not response['ok']:
            return {'energy_remaining': None, 'observations_remaining': None,
                    'wall_seconds_remaining': 0, 'session_ended': True}
        return response['budget']

    def mission(self):
        response = self.environment.request('mission')
        if not response['ok']:
            return response
        data = copy.deepcopy(response['data'])
        if self.task is None:
            if data['task'].get('body_observation_protocol') != 'time_series':
                # Preserve v1-v3 observation semantics for explicit legacy runs.
                data['first_light'].pop('body_observation', None)
                data.pop('body_position_estimate', None)
                data['task'].pop('visible_bodies', None)
                data['task']['body_position_source'] = 'Call observe_body(times) to obtain body positions.'
                data['task']['first_light_note'] = (
                    'Two free standard probe trajectories, each with eight absolute times including t0. '
                    'Repeated mission reads return the same data without resetting the session.')
            self.task = copy.deepcopy(data['task'])
            light = data['first_light']
            if self._time_series_bodies():
                light['body_observation'] = self._acquire_body_observation(light['body_observation'])
            for p in light['probes']:
                self.store.add('probe', p, p['probe_id'])
            self._initial_mission = copy.deepcopy(data)
            (self.run_dir / 'mission.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        data = copy.deepcopy(self._initial_mission)
        data['expression_syntax'] = self.expression_syntax()
        response['data'] = data
        return response

    @staticmethod
    def expression_syntax():
        return ('law_spec={ax:expression,ay:expression}. Both may use t,x,y,vx,vy. '
                'Operators + - * / **; functions sin,cos,exp,log,sqrt,abs. '
                'sum_b(expression) uses bx,by at the current absolute integration time t, from acquired body states. '
                'For time-series missions, initial states and first-light body observations are free; '
                'observe_body(times) adds measured epochs. Linear interpolation requires observations covering the full rollout interval; no extrapolation. '
                'Legacy missions without acquired body positions require observe_body first. '
                "q('name') reads a public allowed scalar property: mass or charge when provided. "
                'No attributes, indexing, imports or code. All coefficients and offsets must be named fitted parameters '
                '(at most 5, parameter_spec list of {name,initial,lower?,upper?}). '
                'Only structural literals 0,1 and integer exponents -3..3; no constant arithmetic or nonzero literal offsets. '
                'Both components together allow at most 256 AST nodes and depth 16. '
                'A syntax/resource rejection does not test the physical hypothesis; simplify an equivalent expression before changing the hypothesis. '
                'For example a velocity-only candidate ax=-d*vx,ay=-d*vy is syntactically legal; '
                'this is a grammar example, not evidence about this universe. Initial conditions and times use mission units.')

    def execute(self, name, args):
        started = time.monotonic()
        try:
            schema = next((s['function']['parameters'] for s in self.schemas if s['function']['name'] == name), None)
            if schema is None:
                raise ValueError('Unknown tool')
            # JSON encoder also rejects nonfinite numbers supplied by a permissive parser.
            json.dumps(args, allow_nan=False)
            validate(args, schema)
            budget = self.budget()
            if self.session_ended or budget['session_ended'] or budget['wall_seconds_remaining'] <= 0:
                raise ValueError('Session ended or wall time exhausted')
            if self.task is None:
                raise ValueError('Framework must initialize mission first')
            result = getattr(self, name)(**args)
            if self.budget()['wall_seconds_remaining'] <= 0 and not self.session_ended:
                raise ValueError('Session wall time exhausted during tool execution')
            response = {'ok': True, 'data': result, 'error': None, 'budget': self.budget()}
        except Exception as exc:
            response = {'ok': False, 'data': None, 'error': {'code': getattr(exc, 'code', type(exc).__name__),
                        'message': str(exc)[:1500]}, 'budget': self.budget()}
        try:
            json.dumps(args, allow_nan=False)
            logged_args = args
        except (ValueError, TypeError):
            logged_args = {'invalid_arguments': 'not finite JSON; omitted from audit'}
        append_event(self.run_dir / 'tools.jsonl', {'tool': name, 'arguments': logged_args, 'result': response,
                                                  'elapsed_seconds': time.monotonic()-started})
        return response

    def _environment_call(self, name, **kwargs):
        response = self.environment.request(name, **kwargs)
        if not response['ok']:
            raise ValueError(str(response['error']))
        return response['data']

    def observe_body(self, times):
        obs = self._environment_call('observe_body', times=times)
        return preview(self._acquire_body_observation(obs))

    def _time_series_bodies(self):
        return bool(self.task and self.task.get('body_observation_protocol') == 'time_series')

    def _body_inputs(self, law=None):
        # Source states are experiment inputs, not fitted force parameters. Each
        # new validation records its own input snapshot; old law records stay fixed.
        if law is not None and law.get('body_input_protocol') != 'instantaneous_visible_state':
            return law['known_bodies']
        if self._time_series_bodies():
            return copy.deepcopy(self.body_position_estimate)
        return copy.deepcopy(self.known_bodies)

    def _acquire_body_observation(self, observation):
        records = list(self.store.records['body_observation'].values()) + [observation]
        if self._time_series_bodies():
            estimate = estimate_body_trajectories(records, self.task.get('body_initial_states'),
                                                  self.task.get('position_noise_sigma'))
        else:
            if self.task.get('static_visible_bodies') is not True:
                raise ValueError('Static position estimation requires explicitly static bodies')
            estimate = estimate_static_bodies(records, self.task.get('position_noise_sigma'))
        acquired = copy.deepcopy(observation)
        acquired['body_position_estimate'] = copy.deepcopy(estimate)
        self.store.add('body_observation', acquired, observation['observation_id'])
        self.body_position_estimate = estimate
        self.known_bodies = [{'body_id': b['body_id'], 'position': list(b['position'])}
                             for b in estimate['bodies']]
        return acquired

    def insert_probe(self, probes, t0, dt, n_samples):
        data = self._environment_call('insert_probe', probes=probes, t0=t0, dt=dt, n_samples=n_samples)
        trajectories = data['probes'] if isinstance(data, dict) else data
        for probe in trajectories:
            self.store.add('probe', probe, probe['probe_id'])
        return {'probes': [preview(p) for p in trajectories]}

    def _probes(self, ids):
        if len(ids) != len(set(ids)) or not ids:
            raise ValueError('Specify distinct existing probe ids')
        return [self.store.get('probe', rid) for rid in ids]

    def fit_law_and_rollout(self, law_spec, parameter_spec, train_probe_ids):
        probes = self._probes(train_probe_ids)
        if not self.known_bodies:
            expression = Expression(law_spec, parameter_spec)
            if any(isinstance(node, ast.Name) and node.id == 'sum_b'
                   for tree in expression.nodes for node in ast.walk(tree)):
                raise ValueError('No body positions acquired; call observe_body(times) before fitting with sum_b.')
        body_inputs = self._body_inputs()
        result = numerics.fit(law_spec, parameter_spec, probes, body_inputs,
                              max_nfev=self.config.get('max_nfev', 80),
                              timeout_seconds=min(25.0, self.budget()['wall_seconds_remaining']),
                              position_noise_sigma=self.task.get('position_noise_sigma'))
        # Versions are numbered within a session; never reuse an archived ID.
        law_ids = set(self.store.records['law'])
        law_ids.update(p.stem for p in (self.store.directory / 'law').glob('*.json'))
        serials = [int(item[4:]) for item in law_ids
                   if item.startswith('law_') and item[4:].isdigit()]
        rid = f'law_{max([len(law_ids), *serials]) + 1}'
        record = dict(result, law_id=rid, law_spec=law_spec, parameter_spec=parameter_spec,
                      train_probe_ids=train_probe_ids, known_bodies=copy.deepcopy(self.known_bodies),
                      body_position_estimate=copy.deepcopy(self.body_position_estimate))
        if self._time_series_bodies():
            record.update(body_context=body_inputs, body_input_protocol='instantaneous_visible_state')
        self.store.add('law', record, rid)
        return preview(record)

    def _law(self, law_id):
        law = self.store.get('law', law_id)
        if not law.get('fitted_parameters') and law.get('parameter_spec'):
            raise ValueError('Law has no fitted parameters')
        if law.get('fit_status') in ('failed', 'error'):
            raise ValueError('Cannot use failed fit')
        return law

    def validate_law(self, law_id, test_probe_ids):
        law = self._law(law_id)
        if set(test_probe_ids) & set(law['train_probe_ids']):
            raise ValueError('Training and validation trajectories overlap')
        probes = self._probes(test_probe_ids)
        body_inputs = self._body_inputs(law)
        rollouts = [numerics.rollout(law['law_spec'], law['fitted_parameters'], p, body_inputs,
                                    timeout_seconds=self.budget()['wall_seconds_remaining']) for p in probes]
        rid = 'validation_' + uuid.uuid4().hex[:12]
        data = {'validation_id': rid, 'law_id': law_id, 'test_probe_ids': test_probe_ids,
                'errors': numerics.errors_for_rollouts(probes, rollouts), 'rollouts': rollouts,
                'warnings': ['Errors are relative to observations, not hidden truth. No pass threshold is defined.',
                             'Changing a model after seeing these data makes them development data; use fresh experiments for final checking.']}
        if law.get('body_input_protocol') == 'instantaneous_visible_state':
            data.update(body_context=body_inputs, body_input_protocol='instantaneous_visible_state')
            data['warnings'].append('Force formula and parameters are frozen; visible source states use the acquired observation snapshot saved in this validation. Interpolation error is part of the input uncertainty.')
        self.store.add('validation', data, rid)
        return preview(data)

    def call_back(self, record_type='all', record_ids=None, detail='summary'):
        return {'records': self.store.query(record_type, record_ids, detail)}

    def analyze_residual(self, law_id, probe_ids):
        law = self._law(law_id)
        body_inputs = self._body_inputs(law)
        data = []
        for p in self._probes(probe_ids):
            pred = numerics.rollout(law['law_spec'], law['fitted_parameters'], p, body_inputs,
                                    timeout_seconds=self.budget()['wall_seconds_remaining'])
            res = {'r': np.asarray(pred['r_pred'])-p['r_obs'], 'v': np.asarray(pred['v_pred'])-p['v_obs'],
                   'a': np.asarray(pred['a_pred'])[1:-1]-np.asarray(p['a_est']).reshape(-1, 2)}
            features = np.column_stack([p['times'], p['r_obs'], p['v_obs']])
            correlations = {}
            for name, values in res.items():
                f = features[1:-1] if name == 'a' else features
                correlations[name] = {axis: {feature: correlation(values[:, j], f[:, k])
                   for k, feature in enumerate(('t', 'x', 'y', 'vx', 'vy'))} for j, axis in enumerate(('x', 'y'))}
            data.append({'probe_id': p['probe_id'], 'used_for_fit': p['probe_id'] in law['train_probe_ids'],
                         'times': p['times'], 'a_est_times': p['a_est_times'],
                         'residuals': {k: v.tolist() for k,v in res.items()},
                         'statistics': {k: statistics(v) for k,v in res.items()}, 'correlations': correlations})
        rid = 'residual_' + uuid.uuid4().hex[:12]
        record = {'residual_id': rid, 'law_id': law_id, 'probe_ids': probe_ids, 'trajectories': data,
                  'description': 'Prediction minus observation; acceleration prediction minus central-difference estimate.',
                  'warnings': ['Correlation is not causation; acceleration estimates have differencing bias.',
                               'Missing acceleration samples and constant-variable correlations are undefined.']}
        if law.get('body_input_protocol') == 'instantaneous_visible_state':
            record.update(body_context=body_inputs, body_input_protocol='instantaneous_visible_state')
        self.store.add('residual', record, rid)
        return preview(record)

    def run_code(self, code, inputs, output_schema):
        import hashlib
        from .code_execution import execute_code, validate_output_schema
        if not self.code_enabled:
            raise ValueError('Code execution is disabled')
        validate_output_schema(output_schema)
        loaded, provenance = {}, {}
        for alias, reference in inputs.items():
            loaded[alias] = [self.store.get(reference['record_type'], rid) for rid in reference['record_ids']]
            provenance[alias] = dict(reference, sha256=[hashlib.sha256(
                json.dumps(item, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
                for item in loaded[alias]])
        rid = 'code_' + uuid.uuid4().hex[:12]
        parent = self.run_dir / 'code_executions' / rid
        parent.mkdir(parents=True, exist_ok=False)
        (parent / 'analysis.py').write_text(code, encoding='utf-8')
        (parent / 'inputs.json').write_text(json.dumps(loaded, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        (parent / 'output_schema.json').write_text(json.dumps(output_schema), encoding='utf-8')
        try:
            result = execute_code(code, loaded, output_schema, parent / 'artifacts', self.code_config,
                                  max(0, self.budget()['wall_seconds_remaining'] - 10))
        except (ValueError, OSError) as exc:
            result = {'status': 'unavailable', 'result': None, 'error': {'type': type(exc).__name__,
                      'message': str(exc)[:1500]}, 'stdout': '', 'stderr': '', 'artifacts': []}
        record = dict(result, execution_id=rid, code=code, inputs=provenance,
                      output_schema=output_schema,
                      meaning='Computed from acquired data; not an independent experiment or correctness verdict.')
        self.store.add('code_execution', record, rid)
        return preview(record)

    def submit(self, law_id, claims, physical_explanation):
        from .submission import export_submission
        law = self._law(law_id)
        rid = 'submission_' + uuid.uuid4().hex[:12]
        try:
            checks = export_submission(self.run_dir / 'submissions' / rid, law, claims,
                                       self._probes(law['train_probe_ids']), physical_explanation)
            if self.budget()['wall_seconds_remaining'] <= 0:
                raise ValueError('Wall time exhausted during submission checks')
            ended = self._environment_call('end_session')
            self.session_ended = True
            status, reasons = 'accepted', []
        except Exception as exc:
            checks, status, reasons = {}, 'rejected', [str(exc)[:1000]]
        data = {'submission_id': rid, 'law_id': law_id, 'claims': claims,
                'physical_explanation': physical_explanation, 'status': status,
                'checks': checks, 'reasons': reasons, 'session_ended': self.session_ended,
                'meaning': 'Local acceptance only; no truth or hidden-test check was performed.'}
        self.store.add('submission', data, rid)
        return data
