"""Observation-only numerical diagnostics; never produce a fitted submission law.

The inputs are acquired probe records and public task metadata. No simulator,
world catalog, filesystem, historical run or evaluation access is used here.
"""
from __future__ import annotations

import math
import numpy as np


RCOND = 1e-10
CONDITION_WARNING = 1e8
MAX_PROBES = 102
MAX_SAMPLES = 1000


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _prepare(probes, task):
    if not isinstance(probes, list) or not 1 <= len(probes) <= MAX_PROBES:
        raise ValueError('Specify 1 to 102 acquired probes')
    names = task.get('allowed_properties', [])
    if not isinstance(names, list) or len(names) > 16 or any(not isinstance(x, str) for x in names):
        raise ValueError('Invalid public allowed_properties')
    names = sorted(set(names))
    controls = task.get('property_controls', {})
    rows, identifiers = [], set()
    for probe in probes:
        pid = probe.get('probe_id')
        if not isinstance(pid, str) or not pid or pid in identifiers:
            raise ValueError('Probe identifiers must be nonempty and distinct')
        identifiers.add(pid)
        t = np.asarray(probe.get('times'), dtype=float)
        r = np.asarray(probe.get('r_obs'), dtype=float)
        v = np.asarray(probe.get('v_obs'), dtype=float)
        if (t.ndim != 1 or not 2 <= len(t) <= MAX_SAMPLES or r.shape != (len(t), 2)
                or v.shape != r.shape or not all(np.isfinite(a).all() for a in (t, r, v))
                or not np.all(np.diff(t) > 0)):
            raise ValueError('Each probe needs finite increasing times and matching 2D position/velocity readouts')
        if max(float(np.max(np.abs(a))) for a in (t, r, v)) > 1e12:
            raise ValueError('Observation magnitudes exceed diagnostic numerical bounds')
        initial = probe.get('initial_conditions', {})
        properties = initial.get('properties', {})
        values = {}
        for name in names:
            control = controls.get(name, {})
            value = properties.get(name, control.get('default'))
            values[name] = float(value) if _number(value) else None
        rows.append({'id': pid, 't': t, 'r': r, 'v': v, 'properties': values})
    return sorted(rows, key=lambda row: row['id']), names


def _weights(groups):
    """Equal trajectory weight, then equal interval weight within each trajectory."""
    return np.concatenate([np.full(len(x), 1 / math.sqrt(len(groups) * len(x))) for x in groups])


def _solve(xs, ys):
    x, y = np.concatenate(xs), np.concatenate(ys)
    weights = _weights(xs)
    wx, wy = x * weights[:, None], y * weights[:, None]
    scales = np.linalg.norm(wx, axis=0)
    scales = np.where(scales > 0, scales, 1.)
    scaled = wx / scales
    coefficients, _, rank, singular = np.linalg.lstsq(scaled, wy, rcond=RCOND)
    coefficients = coefficients / scales[:, None]
    full_rank = int(rank) == x.shape[1]
    condition = float(singular[0] / singular[-1]) if full_rank and singular[-1] > 0 else None
    reliable = full_rank and condition <= CONDITION_WARNING
    return coefficients, {'rank': int(rank), 'n_columns': x.shape[1], 'full_column_rank': full_rank,
                          'condition_number': condition, 'condition_warning_threshold': CONDITION_WARNING,
                          'coefficient_identifiability': 'full_rank_design' if reliable else 'not_unique_or_unstable',
                          'column_scales': scales.tolist(), 'singular_values': singular.tolist(),
                          'svd_relative_cutoff': RCOND}, reliable


def _errors(residuals, targets):
    mse = float(np.mean([np.mean(np.sum(a*a, axis=1)) for a in residuals]))
    reference = float(np.sqrt(np.mean([np.mean(np.sum(a*a, axis=1)) for a in targets])))
    rmse = math.sqrt(mse)
    return {'delta_velocity_vector_rmse': rmse, 'observed_delta_velocity_vector_rms': reference,
            'relative_rmse': rmse / reference if reference > 0 else None,
            'relative_rmse_unavailable_reason': None if reference > 0 else 'zero_observed_velocity_increment'}


def _basis(degree):
    return [(i, power-i) for power in range(degree+1) for i in range(power, -1, -1)]


def _term(i, j):
    return '*'.join([f'{name}^{power}' if power != 1 else name
                     for name, power in (('x', i), ('y', j)) if power]) or '1'


def _spatial(rows):
    # Normalization changes conditioning, not the complete polynomial span.
    scale = np.sqrt(np.mean([np.mean(row['r']**2, axis=0) for row in rows], axis=0))
    scale = np.where(scale > 0, scale, 1.)
    ys = [np.diff(row['v'], axis=0) for row in rows]
    models = []
    for degree in (1, 2, 3):
        powers = _basis(degree)
        xs = []
        for row in rows:
            q = row['r'] / scale
            phi = np.column_stack([q[:, 0]**i * q[:, 1]**j for i, j in powers])
            xs.append(.5 * (phi[:-1] + phi[1:]) * np.diff(row['t'])[:, None])
        coefficients, design, reliable = _solve(xs, ys)
        residuals = [x @ coefficients - y for x, y in zip(xs, ys)]
        fitted = []
        if reliable:
            for column, (i, j) in enumerate(powers):
                raw = coefficients[column] / (scale[0]**i * scale[1]**j)
                contribution = math.sqrt(float(np.mean([np.mean(np.sum(
                    (x[:, column, None] * coefficients[column])**2, axis=1)) for x in xs])))
                fitted.append({'term': _term(i, j), 'ax': float(raw[0]), 'ay': float(raw[1]),
                               'delta_velocity_contribution_rms': contribution})
        cv = {'status': 'unavailable', 'reason': 'requires_at_least_two_probe_trajectories',
              'split_unit': 'whole_probe_trajectory', 'folds': []}
        if len(rows) >= 2:
            n_folds = min(5, len(rows))
            held_residuals, held_targets = [], []
            for fold in range(n_folds):
                test = [i for i in range(len(rows)) if i % n_folds == fold]
                train = [i for i in range(len(rows)) if i not in test]
                beta, fold_design, stable = _solve([xs[i] for i in train], [ys[i] for i in train])
                cv['folds'].append({'held_out_probe_ids': [rows[i]['id'] for i in test],
                                    'training_rank': fold_design['rank'],
                                    'training_condition_number': fold_design['condition_number'],
                                    'usable': stable})
                if stable:
                    held_residuals.extend(xs[i] @ beta - ys[i] for i in test)
                    held_targets.extend(ys[i] for i in test)
            complete = all(fold['usable'] for fold in cv['folds'])
            cv.update(status='available' if complete else 'unavailable',
                      reason=None if complete else 'at_least_one_training_fold_is_rank_deficient_or_unstable')
            if complete:
                cv['errors'] = _errors(held_residuals, held_targets)
        models.append({'degree': degree, 'basis': [_term(*p) for p in powers],
                       'coordinate_scales': {'x': float(scale[0]), 'y': float(scale[1])},
                       'design': design, 'training_errors': _errors(residuals, ys),
                       'cross_validation': cv, 'diagnostic_coefficients': fitted if reliable else None,
                       'largest_terms_by_increment_contribution': sorted(fitted, key=lambda c: c['delta_velocity_contribution_rms'], reverse=True)[:6],
                       'coefficient_note': 'ax and ay are independent outputs; no equality, symmetry or shared-axis constraint. '
                                           'Coefficients are in original coordinate units and are diagnostic only, not a submission law.'})
    return {'method': 'Delta-v integral regression; trapezoidal integration on acquired nonuniform time grids',
            'target': 'observed adjacent velocity increments', 'models': models,
            'limitations': ['Spatial-only regression is a restricted hypothesis: velocity, time and varying public properties can confound it.',
                           'Training residuals are not rollout errors. Trapezoidal quadrature has sampling bias even with noise-free readouts.',
                           'Whole-probe cross-validation is development evidence; using it to change a candidate requires fresh final validation.',
                           'The same initial condition or controls across probes can still leave extrapolation untested.',
                           'Polynomial terms are the full monomial dictionary through each degree, not world-specific formulas.']}


def _radial(rows, names, task):
    sigma = task.get('velocity_noise_sigma')
    known_noise = _number(sigma) and sigma >= 0
    sigma = float(sigma) if known_noise else None
    groups, transverse, total, signs = [], [], [], []
    excluded = 0
    for row in rows:
        dt = np.diff(row['t'])
        midpoint = .5 * (row['r'][:-1] + row['r'][1:])
        radius = np.linalg.norm(midpoint, axis=1)
        acceleration = np.diff(row['v'], axis=0) / dt[:, None]
        valid_radius = radius > 0
        radial = np.zeros(len(dt))
        radial[valid_radius] = np.sum(acceleration[valid_radius] * midpoint[valid_radius], axis=1) / radius[valid_radius]
        transverse.append(np.sum(acceleration[valid_radius]**2, axis=1) - radial[valid_radius]**2)
        total.append(np.sum(acceleration[valid_radius]**2, axis=1))
        cutoff = 3 * math.sqrt(2) * sigma / dt if known_noise else np.zeros(len(dt))
        usable = valid_radius & (np.abs(radial) > cutoff)
        excluded += int(np.sum(~usable))
        if np.any(usable):
            groups.append({'radius': radius[usable], 'radial': radial[usable], 'id': row['id'],
                           'properties': row['properties']})
            signs.append(radial[usable])
    out = {'reference_point': [0., 0.], 'reference_point_meaning': 'public coordinate origin; candidate reference, not an inferred force center',
           'acceleration_estimate': '(v[i+1]-v[i])/(t[i+1]-t[i]) at the arithmetic position midpoint; interval approximation, not exact instantaneous acceleration',
           'method': 'log(abs(radial_acceleration)) = intercept + p*log(radius) + sum(alpha*log(positive public property))',
           'velocity_noise_sigma': sigma, 'noise_metadata_available': known_noise,
           'excluded_interval_count': excluded, 'status': 'unavailable',
           'unvaried_controls': [], 'unusable_controls': [],
           'acceleration_magnitude_radius_power': None, 'vector_factor_power': None,
           'usable_for_power_interpretation': False, 'power_interpretation_reasons': [],
           'power_interpretation_screen': 'Only a screening rule for an approximate radial description, not physical identification. Requires a stable log design, transverse RMS fraction <=0.25, consistent radial sign and radius span >=1.2.',
           'power_meaning': 'p is the radial acceleration magnitude exponent; the factor multiplying the displacement vector has exponent p-1. Positive p grows with radius; negative p decreases.',
           'limitations': ['Radial projection around the coordinate origin does not establish a central force or its source.',
                          'Finite differences and midpoint positions have sampling bias; noise in positions also biases regressors.',
                          'Positive-property slopes are conditional empirical associations, not causal effects; constant or confounded controls are not identified.',
                          'Time and velocity dependence can confound a radial power fit. A good in-sample fit is not evidence of global power-law dynamics.']}
    nonempty = [(a, b) for a, b in zip(transverse, total) if len(a)]
    if nonempty:
        numerator = float(np.mean([np.mean(np.maximum(a, 0)) for a, _ in nonempty]))
        denominator = float(np.mean([np.mean(b) for _, b in nonempty]))
        out['transverse_acceleration_rms_fraction'] = math.sqrt(numerator / denominator) if denominator > 0 else None
    else:
        out['transverse_acceleration_rms_fraction'] = None
    if not groups:
        out['reason'] = 'no_nonzero_radial_signal_above_available_noise_cutoff'
        out['power_interpretation_reasons'] = [out['reason']]
        return out
    varying = []
    property_values = {}
    for name in names:
        values = [row['properties'][name] for row in rows]
        if any(value is None or value <= 0 for value in values):
            out['unusable_controls'].append(name)
            property_values[name] = sorted({value for value in values if value is not None})
        else:
            property_values[name] = sorted(set(values))
            if len(set(values)) < 2:
                out['unvaried_controls'].append(name)
            else:
                varying.append(name)
    out['public_property_values'] = property_values
    out['unidentified_property_controls'] = sorted(out['unvaried_controls'] + out['unusable_controls'])
    out['conditional_on_fixed_property_values'] = {name: property_values[name] for name in out['unvaried_controls']}
    out['property_identification_note'] = 'Unvaried or unusable controls have unidentified effects, not zero effects. Fitted property powers remain conditional associations, not causal identification.'
    radius = np.concatenate([g['radius'] for g in groups])
    out['radius_range'] = [float(np.min(radius)), float(np.max(radius))]
    out['radius_span_ratio'] = float(np.max(radius) / np.min(radius))
    out['weak_radius_span'] = out['radius_span_ratio'] < 1.2
    out['outward_radial_fraction'] = float(np.mean([np.mean(a > 0) for a in signs]))
    out['radial_direction'] = ('outward' if out['outward_radial_fraction'] >= .95 else
                               'inward' if out['outward_radial_fraction'] <= .05 else 'mixed')
    xs, ys = [], []
    for group in groups:
        xs.append(np.column_stack([np.ones(len(group['radius'])), np.log(group['radius'])] +
            [np.full(len(group['radius']), math.log(group['properties'][name])) for name in varying]))
        ys.append(np.log(np.abs(group['radial']))[:, None])
    coefficients, design, stable = _solve(xs, ys)
    residuals = [x @ coefficients - y for x, y in zip(xs, ys)]
    out.update(design=design, fitted_features=['intercept', 'log(radius)'] + [f'log({name})' for name in varying],
               log_magnitude_rmse=math.sqrt(float(np.mean([np.mean(a*a) for a in residuals]))),
               used_probe_ids=[g['id'] for g in groups], used_interval_count=sum(len(g['radius']) for g in groups))
    if stable:
        p = float(coefficients[1, 0])
        out.update(status='empirical_fit', acceleration_magnitude_radius_power=p, vector_factor_power=p-1,
                   intercept_log_magnitude=float(coefficients[0, 0]),
                   positive_property_powers={name: float(coefficients[i+2, 0]) for i, name in enumerate(varying)})
    else:
        out['reason'] = 'log_feature_design_rank_deficient_or_unstable'
    reasons = []
    if not stable:
        reasons.append('log_feature_design_rank_deficient_or_unstable')
    if out['transverse_acceleration_rms_fraction'] is None or out['transverse_acceleration_rms_fraction'] > .25:
        reasons.append('substantial_or_unavailable_transverse_acceleration')
    if out['radial_direction'] == 'mixed':
        reasons.append('mixed_radial_sign')
    if out['weak_radius_span']:
        reasons.append('radius_span_below_1_2')
    if out['unusable_controls']:
        reasons.append('some_public_properties_missing_or_nonpositive')
    if not known_noise:
        reasons.append('velocity_noise_metadata_unavailable')
    out['power_interpretation_reasons'] = reasons
    out['usable_for_power_interpretation'] = not reasons
    return out


def diagnose(probes, public_task):
    """Return finite JSON-compatible observation diagnostics without selecting a law."""
    if not isinstance(public_task, dict):
        raise ValueError('public_task must be a mapping')
    rows, names = _prepare(probes, public_task)
    # Check actual results below. Some BLAS implementations leave floating-point
    # status flags set after an otherwise finite rank-deficient solve.
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        result = {'method_version': 'observation_diagnostics_v1',
                  'source': 'only supplied acquired probes and public task metadata',
                  'probe_ids': [row['id'] for row in rows],
                  'space_regression': _spatial(rows), 'radial_diagnostic': _radial(rows, names, public_task),
                  'meaning': 'Exploratory numerical evidence only. No candidate law, submission or official verdict is produced.'}
    def require_finite(value):
        if isinstance(value, dict):
            for item in value.values():
                require_finite(item)
        elif isinstance(value, list):
            for item in value:
                require_finite(item)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Observation diagnostics produced nonfinite values')
    require_finite(result)
    return result
