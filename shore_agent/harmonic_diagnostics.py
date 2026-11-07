"""Optional observation-only harmonic affine-position diagnostic.

This module neither acquires observations nor constructs a submission law. A
freely fitted frequency multiplies the complete spatial basis (1, x, y), with
independent coefficients for both axes. Its cross-validation is reconstruction
of acquired velocity increments, not an independent rollout evaluation.
"""
from __future__ import annotations

import math
import time

import numpy as np
from scipy.optimize import minimize_scalar

from .diagnostics import _errors, _number, _prepare, _solve


BASIS = ['1', 'x', 'y', 'sin(omega*t)', 'x*sin(omega*t)', 'y*sin(omega*t)',
         'cos(omega*t)', 'x*cos(omega*t)', 'y*cos(omega*t)']
MAX_GRID_POINTS = 512
PROFILE_ABSOLUTE_TOLERANCE = 1e-8
PROFILE_RELATIVE_TOLERANCE = .05


class _TimeLimit(Exception):
    pass


def _guard(deadline):
    if time.perf_counter() >= deadline:
        raise _TimeLimit


def _design(rows, omega=None):
    xs, ys = [], []
    for row in rows:
        t, r, v = row['t'], row['r'], row['v']
        dt = np.diff(t)[:, None]
        tm = (t[:-1] + t[1:]) / 2
        rm = (r[:-1] + r[1:]) / 2 + dt * (v[:-1] - v[1:]) / 8
        endpoints, middle = np.column_stack([np.ones(len(t)), r]), np.column_stack([np.ones(len(tm)), rm])
        if omega is not None:
            endpoints = np.column_stack([endpoints, np.sin(omega*t)[:, None]*endpoints,
                                         np.cos(omega*t)[:, None]*endpoints])
            middle = np.column_stack([middle, np.sin(omega*tm)[:, None]*middle,
                                      np.cos(omega*tm)[:, None]*middle])
        xs.append(dt * (endpoints[:-1] + 4*middle + endpoints[1:]) / 6)
        ys.append(np.diff(v, axis=0))
    return xs, ys


def _fit_at(rows, omega, deadline):
    _guard(deadline)
    xs, ys = _design(rows, omega)
    beta, design, stable = _solve(xs, ys)
    _guard(deadline)
    training = _errors([x@beta-y for x, y in zip(xs, ys)], ys)
    return {'omega': omega, 'beta': beta, 'design': design, 'stable': stable,
            'training_errors': training}, xs, ys


def _objective(model):
    value = model['training_errors']['relative_rmse']
    return value if model['stable'] and _number(value) else math.inf


def _coefficients(model, xs, basis):
    if not model['stable']:
        return None
    beta = model['beta']
    return [{'term': name, 'ax': float(beta[column, 0]), 'ay': float(beta[column, 1]),
             'delta_velocity_contribution_rms': math.sqrt(float(np.mean([
                 np.mean(np.sum((x[:, column, None]*beta[column])**2, axis=1)) for x in xs])))}
            for column, name in enumerate(basis)]


def _search(rows, deadline):
    span = max(row['t'][-1] for row in rows) - min(row['t'][0] for row in rows)
    maximum_interval = max(float(np.max(np.diff(row['t']))) for row in rows)
    upper = math.pi / maximum_interval
    if (not math.isfinite(upper) or upper > 1e12
            or upper*max(float(np.max(np.abs(row['t']))) for row in rows) > 1e12):
        raise ValueError('observation time scale exceeds harmonic diagnostic numerical bounds')
    lower = upper * 1e-4
    requested_count = max(48, int(math.ceil(4*upper*span/math.pi)) + 1)
    grid = np.linspace(lower, upper, min(MAX_GRID_POINTS, requested_count))
    cache = {}

    def at(omega):
        omega = float(omega)
        if omega not in cache:
            cache[omega] = _fit_at(rows, omega, deadline)[0]
        return cache[omega]

    sampled = [at(omega) for omega in grid]
    objectives = [_objective(model) for model in sampled]
    local_indices = [i for i, value in enumerate(objectives) if math.isfinite(value)
                     and (i == 0 or value <= objectives[i-1])
                     and (i == len(grid)-1 or value <= objectives[i+1])]
    local_indices.sort(key=lambda i: objectives[i])
    search = {'frequency_lower': lower, 'frequency_upper': upper,
              'observed_time_span': float(span), 'largest_observed_interval': maximum_interval,
              'grid_point_count': len(grid), 'requested_grid_point_count': requested_count,
              'grid_capped': requested_count > MAX_GRID_POINTS,
              'range_rule': 'upper=pi/largest observed interval; lower=upper*1e-4. Grid spacing targets pi/(4*observed span). All values derive from the supplied training probes.',
              'range_scope': 'A conservative sampling-based search band, not a physical frequency bound or an alias-free guarantee on nonuniform/disconnected observation windows.'}
    if not local_indices:
        return None, search, None
    refined = []
    for i in local_indices[:3]:
        lo, hi = grid[max(0, i-1)], grid[min(len(grid)-1, i+1)]
        optimum = minimize_scalar(lambda omega: _objective(at(omega)), bounds=(lo, hi), method='bounded',
                                  options={'xatol': 1e-9, 'maxiter': 50})
        refined.append(at(optimum.x))
    best = min(sampled+refined, key=_objective)
    omega, best_error = best['omega'], _objective(best)
    tolerance = max(PROFILE_ABSOLUTE_TOLERANCE, PROFILE_RELATIVE_TOLERANCE*best_error)
    threshold = best_error+tolerance
    # This is a local profile interval at an explicit engineering loss tolerance,
    # not an uncertainty/confidence interval. Other refined minima are separate.
    def boundary(direction):
        inside = omega
        step = (upper-lower)/(len(grid)-1)
        for _ in range(14):
            outside = max(lower, min(upper, omega+direction*step))
            if _objective(at(outside)) > threshold:
                for _ in range(20):
                    midpoint = (inside+outside)/2
                    if _objective(at(midpoint)) <= threshold:
                        inside = midpoint
                    else:
                        outside = midpoint
                return float(inside)
            inside = outside
            if outside in (lower, upper):
                return float(inside)
            step *= 2
        return float(inside)
    interval = [boundary(-1), boundary(1)]
    near_frequencies = sorted({model['omega'] for model in sampled+refined if _objective(model) <= threshold})
    # Project the frequency derivative away from all independent axis coefficients.
    # A full fixed-frequency design alone does not establish frequency identity.
    step = max(1e-7, abs(omega)*1e-5)
    xs, ys = _design(rows, omega)
    plus, _ = _design(rows, omega+step)
    minus, _ = _design(rows, omega-step)
    derivative = [(a-b)/(2*step)@best['beta'] for a, b in zip(plus, minus)]
    _guard(deadline)
    projection, _, _ = _solve(xs, derivative)
    sensitivity = _errors([d-x@projection for x, d in zip(xs, derivative)], ys)['relative_rmse']
    reasons = []
    if requested_count > MAX_GRID_POINTS:
        reasons.append('frequency_grid_capped_search_may_miss_narrow_minima')
    if interval[0] <= lower or interval[1] >= upper:
        reasons.append('profile_reaches_search_boundary')
    if (interval[1]-interval[0])*span > .5:
        reasons.append('broad_local_frequency_profile')
    if near_frequencies and (near_frequencies[-1]-near_frequencies[0])*span > .5:
        reasons.append('separated_near_best_frequencies_or_broad_profile')
    if not _number(sensitivity) or sensitivity*upper < 1e-6:
        reasons.append('frequency_effect_too_small_after_refitting_linear_coefficients')
    identification = {
        'status': 'locally_resolved_within_searched_family' if not reasons else 'unresolved',
        'reasons': reasons, 'local_profile_interval': interval,
        'near_best_sampled_or_refined_frequencies': near_frequencies,
        'profile_relative_rmse_tolerance': tolerance,
        'profile_tolerance_rule': 'max(1e-8, 0.05*best reconstruction relative RMSE); engineering resolution only, not a confidence interval',
        'profiled_frequency_derivative_relative_rms': sensitivity,
        'global_frequency_uniqueness_established': False,
        'unrefined_sampled_local_minima_count': max(0, len(local_indices)-len(refined)),
        'scope': 'Local identification at the best searched minimum only. At most the three lowest stable grid minima are refined; other valleys, unsearched frequencies and narrow aliases between grid samples are not excluded.'}
    search.update(refined_local_minima_count=len(refined), sampled_local_minima_count=len(local_indices),
                  objective_evaluation_count=len(cache),
                  profile=[{'omega': model['omega'], 'relative_rmse': model['training_errors']['relative_rmse'],
                            'full_rank_stable_design': model['stable']} for model in sampled+refined])
    return best, search, identification


def _model_record(model, rows, basis):
    xs, _ = _design(rows, model['omega'])
    terms = _coefficients(model, xs, basis)
    return {'basis': list(basis), 'design': model['design'], 'training_errors': model['training_errors'],
            'diagnostic_coefficients': terms,
            'largest_terms_by_increment_contribution': sorted(terms or [], key=lambda item: item['delta_velocity_contribution_rms'], reverse=True)[:6]}


def _cross_validate(rows, deadline, harmonic):
    cv = {'status': 'unavailable', 'split_unit': 'whole_probe_trajectory', 'folds': [],
          'errors': None, 'frequency_identification_in_all_folds': None}
    if len(rows) < 2:
        cv['reason'] = 'requires_at_least_two_probe_trajectories'
        return cv
    residuals, targets = [], []
    for fold in range(min(5, len(rows))):
        training = [row for i, row in enumerate(rows) if i % min(5, len(rows)) != fold]
        held = [row for i, row in enumerate(rows) if i % min(5, len(rows)) == fold]
        if harmonic:
            model, search, identification = _search(training, deadline)
        else:
            model, _, _ = _fit_at(training, None, deadline)
            search, identification = None, None
        usable = model is not None and model['stable']
        cv['folds'].append({'held_out_probe_ids': [row['id'] for row in held],
                            'usable': usable, 'usable_for_reconstruction_error': usable,
                            'selected_omega': model['omega'] if usable else None,
                            'training_rank': model['design']['rank'] if model else None,
                            'training_condition_number': model['design']['condition_number'] if model else None,
                            'frequency_search': {key: search[key] for key in ('frequency_lower', 'frequency_upper', 'grid_capped')} if search else None,
                            'frequency_identification': identification})
        if usable:
            xs, ys = _design(held, model['omega'])
            residuals.extend(x@model['beta']-y for x, y in zip(xs, ys))
            targets.extend(ys)
    if all(fold['usable'] for fold in cv['folds']):
        cv.update(status='available', errors=_errors(residuals, targets))
    else:
        cv['reason'] = 'at_least_one_training_fold_rank_deficient_or_unstable'
    if harmonic:
        cv['frequency_identification_in_all_folds'] = all(
            fold['usable'] and fold['frequency_identification']['status'] == 'locally_resolved_within_searched_family'
            for fold in cv['folds'])
        cv['frequency_caution'] = 'Available errors measure the whole frequency-selection procedure; an unresolved fold frequency prevents claiming a uniquely identified frequency even if its reconstruction error is small.'
    return cv


def diagnose_harmonic(probes, public_task, *, max_seconds=2.0):
    """Return a bounded optional diagnostic using only supplied acquired data.

    Both noise standard deviations must explicitly be zero. The default 2-second
    wall budget includes preparation, all frequency searches and whole-probe CV;
    exhaustion is reported without publishing a partial CV as complete.
    """
    started = time.perf_counter()
    if not isinstance(public_task, dict):
        raise ValueError('public_task must be a mapping')
    if not _number(max_seconds) or not 0 < max_seconds <= 10:
        raise ValueError('max_seconds must be positive and at most 10')
    noise = [public_task.get(key) for key in ('position_noise_sigma', 'velocity_noise_sigma')]
    if any(not _number(value) or value != 0 for value in noise):
        raise ValueError('harmonic diagnostics require both position_noise_sigma and velocity_noise_sigma explicitly equal to zero')
    deadline = started+max_seconds
    rows, names = _prepare(probes, public_task)
    property_values = {name: sorted({row['properties'][name] for row in rows if row['properties'][name] is not None}) for name in names}
    result = {
        'method_version': 'harmonic_observation_diagnostics_v1', 'status': 'incomplete',
        'source': 'Only supplied acquired positions, velocities, times and public task metadata.',
        'probe_ids': [row['id'] for row in rows], 'public_property_values': property_values,
        'unvaried_controls': [name for name in names if len(property_values[name]) < 2],
        'basis_family': '(1,x,y) times (1,sin(omega*t),cos(omega*t)); independent ax/ay coefficients and one freely selected positive omega',
        'quadrature': 'Cubic-Hermite position midpoints from observed endpoint r/v, then Simpson integration of each basis term; no new observations or simulator calls.',
        'autonomous_linear_reference': None, 'harmonic_model': None,
        'linear_cv_divided_by_harmonic_cv': None,
        'limitations': [
            'Both position and velocity noise metadata must explicitly equal zero. Measured velocity is assumed to equal the time derivative of position.',
            'Held-out observed velocities also enter Hermite midpoints. Whole-probe CV is observation reconstruction, not independent rollout validation.',
            'Temporal harmonic coefficients do not establish a physical time-dependent force; moving sources or other omitted variables may produce similar observations.',
            'Velocity, public-property and body-position dependence are absent from this dictionary, not proven absent from the dynamics.',
            'A finite frequency band and grid do not rule out aliases, especially for sparse/nonuniform sampling or separated time windows. Profile ranges are not confidence intervals.',
            'Eighteen independent linear coefficients plus frequency can exceed the five-parameter law limit. Any sharing or pruning is a new hypothesis needing formal fit and fresh validation.',
            'Repeated or overlapping trajectories may leave controlled conditions duplicated across probe folds; whole-probe splitting alone does not test all extrapolations.',
        ],
        'meaning': 'Exploratory coefficients and frequency evidence only; no law, selected final answer, submission or official verdict is produced.'}
    try:
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            reference, _, _ = _fit_at(rows, None, deadline)
            result['autonomous_linear_reference'] = _model_record(reference, rows, BASIS[:3])
            result['autonomous_linear_reference']['cross_validation'] = _cross_validate(rows, deadline, False)
            zero_signal = reference['training_errors']['observed_delta_velocity_vector_rms'] == 0
            if zero_signal:
                model, search, identification = None, None, None
            else:
                model, search, identification = _search(rows, deadline)
            if model is None:
                result.update(status='unavailable', reason='zero_observed_velocity_increment' if zero_signal else 'no_full_rank_stable_frequency_design', frequency_search=search)
            else:
                record = _model_record(model, rows, BASIS)
                record.update(omega=model['omega'], frequency_search=search, frequency_identification=identification)
                # Publish the model only with explicitly unavailable CV until all
                # folds finish, so a deadline cannot leave a misleading partial CV.
                record['cross_validation'] = {'status': 'unavailable', 'reason': 'not_completed', 'errors': None}
                result['harmonic_model'] = record
                record['cross_validation'] = _cross_validate(rows, deadline, True)
                before = (result['autonomous_linear_reference']['cross_validation'].get('errors') or {}).get('relative_rmse')
                after = (record['cross_validation'].get('errors') or {}).get('relative_rmse')
                if _number(before) and _number(after) and min(before, after) > 1e-12:
                    result['linear_cv_divided_by_harmonic_cv'] = before/after
                _guard(deadline)
                result['status'] = 'descriptive_comparison'
    except _TimeLimit:
        result.update(status='budget_exhausted', reason='diagnostic_wall_budget_exhausted')
        if result['harmonic_model'] is not None:
            result['harmonic_model']['cross_validation'] = {'status': 'unavailable', 'reason': 'diagnostic_wall_budget_exhausted', 'errors': None}
        result['linear_cv_divided_by_harmonic_cv'] = None
    result['computation'] = {'elapsed_seconds': time.perf_counter()-started, 'wall_budget_seconds': max_seconds,
                              'note': 'The guard runs between numerical operations; one in-flight NumPy/SciPy operation may slightly overrun the budget.'}
    def finite(value):
        if isinstance(value, dict):
            return all(finite(item) for item in value.values())
        if isinstance(value, list):
            return all(finite(item) for item in value)
        return not isinstance(value, float) or math.isfinite(value)
    if not finite(result):
        raise ValueError('Harmonic diagnostics produced nonfinite values')
    return result


def summarize_harmonic(diagnostics):
    """Small model-facing view; all nine coefficient pairs remain available.

    Coefficients are a mapping rather than a long list so ordinary list previews
    cannot silently hide later sine/cosine terms. The full frequency scan stays
    in the original diagnostic record, and no coefficient is thresholded here.
    """
    def relative(errors):
        return (errors or {}).get('relative_rmse')

    def cv_summary(model):
        cv = model.get('cross_validation', {})
        return {'status': cv.get('status'), 'reason': cv.get('reason'),
                'relative_delta_velocity_rmse': relative(cv.get('errors')),
                'frequency_identification_in_all_folds': cv.get('frequency_identification_in_all_folds'),
                'folds': [{'held_out_probe_ids': list(fold['held_out_probe_ids']),
                           'usable_for_reconstruction_error': fold.get('usable_for_reconstruction_error', fold.get('usable')),
                           'omega': fold.get('selected_omega'), 'training_rank': fold.get('training_rank'),
                           'training_condition_number': fold.get('training_condition_number'),
                           'frequency_identification_status': (fold.get('frequency_identification') or {}).get('status'),
                           'frequency_identification_reasons': list((fold.get('frequency_identification') or {}).get('reasons', []))}
                          for fold in cv.get('folds', [])]}

    result = {'summary_version': 'harmonic_observation_summary_v1', 'status': diagnostics['status'],
              'reason': diagnostics.get('reason'), 'probe_ids': list(diagnostics['probe_ids']),
              'autonomous_linear_reference': None, 'harmonic_model': None,
              'linear_cv_divided_by_harmonic_cv': diagnostics.get('linear_cv_divided_by_harmonic_cv'),
              'unvaried_controls': list(diagnostics.get('unvaried_controls', [])),
              'meaning': diagnostics['meaning'],
              'warnings': [
                  'CV compares reconstruction procedures on whole held-out probes; held-out velocities also construct Hermite midpoints. Formal trajectory fit and fresh validation remain necessary.',
                  'A low CV error is compatible with an unresolved frequency. Check frequency_identification_in_all_folds separately; a local profile is neither global uniqueness nor a confidence interval.',
                  'Only the three lowest stable grid minima are refined. Unsearched/narrow aliases and frequencies outside the sampling-derived band remain possible.',
                  'All nine coefficient pairs are shown without pruning. Eighteen independent coefficients plus omega exceed five law parameters; any pruning or signed sharing is a new testable hypothesis.',
                  'Velocity, body and property effects are not included or ruled out. Fixed properties remain unidentified; sparse/disconnected time windows can confound time dependence.',
              ]}
    reference = diagnostics.get('autonomous_linear_reference')
    if reference is not None:
        result['autonomous_linear_reference'] = {
            'training_relative_delta_velocity_rmse': relative(reference.get('training_errors')),
            'cross_validation': cv_summary(reference)}
    model = diagnostics.get('harmonic_model')
    if model is not None:
        identification, search = model['frequency_identification'], model['frequency_search']
        result['harmonic_model'] = {
            'omega': model['omega'], 'rank': model['design']['rank'],
            'condition_number': model['design']['condition_number'],
            'training_relative_delta_velocity_rmse': relative(model.get('training_errors')),
            'coefficients_by_term': {item['term']: {key: item[key] for key in ('ax', 'ay', 'delta_velocity_contribution_rms')}
                                     for item in model.get('diagnostic_coefficients') or []},
            'cross_validation': cv_summary(model),
            'frequency_identification': {key: identification.get(key) for key in (
                'status', 'reasons', 'local_profile_interval', 'profile_relative_rmse_tolerance',
                'global_frequency_uniqueness_established', 'unrefined_sampled_local_minima_count', 'scope')},
            'frequency_search': {key: search.get(key) for key in (
                'frequency_lower', 'frequency_upper', 'grid_point_count', 'grid_capped',
                'refined_local_minima_count', 'sampled_local_minima_count', 'range_rule', 'range_scope')},
        }

    def compact(value):
        if isinstance(value, dict):
            return {key: compact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [compact(item) for item in value]
        if isinstance(value, float):
            return float(f'{value:.8g}')
        return value
    return compact(result)
