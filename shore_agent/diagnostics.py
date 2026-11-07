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


def summarize(diagnostics):
    """Compact model-facing projection; the complete diagnostic remains unchanged."""
    models = diagnostics['space_regression']['models']
    linear = next((m for m in models if m['degree'] == 1), None)
    linear_cv = ((linear or {}).get('cross_validation', {}).get('errors') or {}).get('relative_rmse')
    comparisons = []
    for model in models:
        cv = model['cross_validation']
        cv_relative = (cv.get('errors') or {}).get('relative_rmse')
        improvement = (linear_cv / cv_relative if _number(linear_cv) and _number(cv_relative)
                       and cv_relative > 0 else None)
        if improvement is not None and not math.isfinite(improvement):
            improvement = None
        comparisons.append({
            'degree': model['degree'], 'basis_term_count': len(model['basis']),
            'rank': model['design']['rank'], 'condition_number': model['design']['condition_number'],
            'coefficient_identifiability': model['design']['coefficient_identifiability'],
            'training_relative_delta_velocity_rmse': model['training_errors']['relative_rmse'],
            'whole_probe_cv_status': cv['status'], 'whole_probe_cv_reason': cv.get('reason'),
            'whole_probe_cv_relative_delta_velocity_rmse': cv_relative,
            'linear_cv_divided_by_this_cv': improvement,
            'largest_terms': [{key: item[key] for key in ('term', 'ax', 'ay')}
                              for item in model['largest_terms_by_increment_contribution'][:6]],
        })
    radial = diagnostics['radial_diagnostic']
    log_rmse = radial.get('log_magnitude_rmse')
    scatter_factor = None
    if _number(log_rmse):
        try:
            scatter_factor = math.exp(log_rmse)
        except OverflowError:
            pass
    result = {
        'summary_version': 'observation_diagnostics_summary_v1',
        'probe_ids': list(diagnostics['probe_ids']),
        'spatial_model_comparison': comparisons,
        'comparison_notes': [
            'Compare whole-probe CV errors across degrees, including nonlinear terms that improve held-out prediction; training error alone is insufficient.',
            'The ratio linear_cv_divided_by_this_cv is an error ratio, not confidence or a score; ratios near numerical precision may not be meaningful.',
            'ax and ay coefficients are independent. Terms are sorted by velocity-increment contribution; full basis, coefficients and CV splits are in the saved diagnostic file.',
            'These are approximate velocity-increment regressions, not integrated-trajectory validation. Any scientific candidate still needs formal fit_law_and_rollout and validate_law on new probes.',
        ],
        'radial_power_summary': {
            'reference_point': radial['reference_point'],
            'reference_point_meaning': radial['reference_point_meaning'],
            'empirical_fit_status': radial['status'], 'unavailable_reason': radial.get('reason'),
            'geometry_and_design_screen_satisfied': radial['usable_for_power_interpretation'],
            'screen_reasons': radial['power_interpretation_reasons'],
            'screen_scope': 'Geometry/design screening is NOT a goodness-of-fit check. Even a true screen does not establish a single power law; inspect the log residual below.',
            'acceleration_magnitude_radius_power': radial['acceleration_magnitude_radius_power'],
            'vector_factor_power': radial['vector_factor_power'],
            'power_meaning': radial['power_meaning'],
            'positive_property_powers': radial.get('positive_property_powers'),
            'unidentified_property_controls': radial.get('unidentified_property_controls', []),
            'conditional_on_fixed_property_values': radial.get('conditional_on_fixed_property_values', {}),
            'log_magnitude_rmse': log_rmse,
            'exp_log_rmse_multiplicative_factor': scatter_factor,
            'scatter_factor_meaning': 'exp(log RMSE), a residual scale only; neither an average relative error nor a fit acceptance threshold.',
            'transverse_acceleration_rms_fraction': radial['transverse_acceleration_rms_fraction'],
            'radius_range': radial.get('radius_range'),
        },
        'meaning': diagnostics['meaning'],
    }

    def compact(value):
        if isinstance(value, dict):
            return {key: compact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [compact(item) for item in value]
        if isinstance(value, float):
            return float(f'{value:.6g}')
        return value

    if 'radial_curvature' in diagnostics:
        curvature = diagnostics['radial_curvature']
        result['radial_curvature_summary'] = {
            'status': curvature['status'], 'reason': curvature.get('reason'),
            'geometry_screen_satisfied': curvature['geometry_screen_satisfied'],
            'geometry_screen_reasons': curvature['geometry_screen_reasons'],
            'observed_radius_range': curvature.get('observed_radius_range'),
            'unidentified_property_controls': curvature['unidentified_property_controls'],
            'conditional_on_fixed_property_values': curvature['conditional_on_fixed_property_values'],
            'models': [{key: model.get(key) for key in (
                'log_radius_degree', 'training_log_magnitude_rmse', 'quadratic_log_radius_coefficient',
                'local_acceleration_magnitude_power_range', 'local_vector_factor_power_range',
                'unidentified_property_controls')}
                | {'whole_probe_cv_status': model['cross_validation']['status'],
                   'whole_probe_cv_log_rmse': model['cross_validation']['log_magnitude_rmse'],
                   'rank': model['design']['rank'], 'columns': model['design']['n_columns'],
                   'coefficient_identifiability': model['design']['coefficient_identifiability']}
                for model in curvature['models']],
            'cv_ratio_linear_over_quadratic': curvature['cv_ratio_linear_over_quadratic'],
            'quadratic_cv_reduction_fraction': curvature['quadratic_cv_reduction_fraction'],
            'cv_ratio_reason': curvature.get('cv_ratio_reason'),
            'meaning': curvature['meaning'],
            'slope_meaning': curvature.get('slope_meaning'),
        }
    return compact(result)


def diagnose_radial_curvature(probes, public_task):
    """Compare empirical log-radius curvature without selecting a force family."""
    if not isinstance(public_task, dict):
        raise ValueError('public_task must be a mapping')
    rows, names = _prepare(probes, public_task)
    radial = _radial(rows, names, public_task)
    output = {'method_version': 'radial_log_curvature_v1', 'status': 'unavailable',
              'reference_point': [0., 0.],
              'meaning': 'Conditional curvature of measured radial projections around the coordinate origin, not an identified force center, submission law or official verdict.',
              'method': 'log(abs(midpoint radial acceleration)) regressed on complete degree-1/degree-2 log-radius polynomials and varied positive public log-properties',
              'probe_ids': [row['id'] for row in rows],
              'unidentified_property_controls': sorted(radial.get('unvaried_controls', []) + radial.get('unusable_controls', [])),
              'conditional_on_fixed_property_values': radial.get('conditional_on_fixed_property_values', {}),
              'geometry_screen_satisfied': radial['usable_for_power_interpretation'],
              'geometry_screen_reasons': radial['power_interpretation_reasons'],
              'models': [], 'cv_ratio_linear_over_quadratic': None,
              'quadratic_cv_reduction_fraction': None,
              'limitations': ['Finite differences and position midpoints have sampling bias even without noise; apparent curvature should be checked with finer readouts.',
                             'Whole-probe CV compares development-data approximations, not integrated trajectories or final validation.',
                             'Constant, missing or confounded properties are not identified; no zero property effect is inferred.',
                             'Time, velocity, unvaried properties and inadequate radius coverage may confound curvature; no force family is selected.']}
    if radial.get('design', {}).get('coefficient_identifiability') == 'not_unique_or_unstable':
        output['unidentified_property_controls'] = list(names)
    noise = [public_task.get(key) for key in ('position_noise_sigma', 'velocity_noise_sigma')]
    if any(not _number(value) or value != 0 for value in noise):
        output['reason'] = 'requires_both_explicitly_noise_free_position_and_velocity_readouts'
        return output
    if not radial['usable_for_power_interpretation']:
        output['reason'] = 'radial_geometry_or_design_screen_not_satisfied'
        return output
    varied = [name for name in names if name not in output['unidentified_property_controls']]
    groups = []
    for row in rows:
        midpoint = .5*(row['r'][:-1]+row['r'][1:])
        radius = np.linalg.norm(midpoint, axis=1)
        acceleration = np.diff(row['v'], axis=0) / np.diff(row['t'])[:, None]
        valid = radius > 0
        ar = np.zeros(len(radius))
        ar[valid] = np.sum(acceleration[valid]*midpoint[valid], axis=1)/radius[valid]
        valid &= np.abs(ar) > 0
        if np.any(valid):
            groups.append({'id': row['id'], 'log_radius': np.log(radius[valid]),
                           'target': np.log(np.abs(ar[valid]))[:, None],
                           'log_properties': [math.log(row['properties'][name]) for name in varied]})
    output['used_probe_ids'] = [group['id'] for group in groups]
    if len(groups) < 2:
        output['reason'] = 'requires_at_least_two_radially_informative_probe_trajectories'
        return output
    low = min(float(np.min(g['log_radius'])) for g in groups)
    high = max(float(np.max(g['log_radius'])) for g in groups)
    output['observed_radius_range'] = [math.exp(low), math.exp(high)]
    output['varied_positive_property_controls'] = varied

    def features(group, center, degree):
        z = group['log_radius']-center
        return np.column_stack([z**power for power in range(degree+1)] +
                               [np.full(len(z), value) for value in group['log_properties']])

    def fit(selected, degree):
        center = float(np.mean([np.mean(group['log_radius']) for group in selected]))
        xs = [features(group, center, degree) for group in selected]
        ys = [group['target'] for group in selected]
        beta, design, stable = _solve(xs, ys)
        return center, beta, design, stable, [x@beta-y for x, y in zip(xs, ys)]

    def error(residuals):
        return math.sqrt(float(np.mean([np.mean(values**2) for values in residuals])))

    for degree in (1, 2):
        center, beta, design, stable, residuals = fit(groups, degree)
        model = {'log_radius_degree': degree, 'design': design,
                 'feature_names': ['1', 'centered_log_radius'] + (['centered_log_radius^2'] if degree == 2 else []) +
                                  [f'log({name})' for name in varied],
                 'log_radius_center': center, 'training_log_magnitude_rmse': error(residuals),
                 'diagnostic_coefficients': None, 'local_acceleration_magnitude_power_range': None,
                 'local_vector_factor_power_range': None,
                 'unidentified_property_controls': (list(output['unidentified_property_controls'])
                                                    if stable else list(names)),
                 'cross_validation': {'split_unit': 'whole_probe_trajectory', 'folds': [],
                                      'status': 'unavailable', 'log_magnitude_rmse': None}}
        if stable:
            q = float(beta[2, 0]) if degree == 2 else 0.
            slopes = [float(beta[1, 0])+2*q*(value-center) for value in (low, high)]
            model.update(diagnostic_coefficients=[float(value) for value in beta[:, 0]],
                         quadratic_log_radius_coefficient=q,
                         local_slopes_at_radius_endpoints=slopes,
                         local_acceleration_magnitude_power_range=[min(slopes), max(slopes)],
                         local_vector_factor_power_range=[min(slopes)-1, max(slopes)-1])
        folds, cv_residuals = min(5, len(groups)), []
        for fold in range(folds):
            train = [group for i, group in enumerate(groups) if i % folds != fold]
            held = [group for i, group in enumerate(groups) if i % folds == fold]
            fold_center, fold_beta, fold_design, fold_stable, _ = fit(train, degree)
            model['cross_validation']['folds'].append({'held_out_probe_ids': [g['id'] for g in held],
                'training_rank': fold_design['rank'], 'training_condition_number': fold_design['condition_number'],
                'usable': fold_stable})
            if fold_stable:
                cv_residuals.extend(features(group, fold_center, degree)@fold_beta-group['target'] for group in held)
        if all(fold['usable'] for fold in model['cross_validation']['folds']):
            model['cross_validation'].update(status='available', log_magnitude_rmse=error(cv_residuals))
        else:
            model['cross_validation']['reason'] = 'at_least_one_training_fold_rank_deficient_or_unstable'
        output['models'].append(model)
    output['status'] = 'descriptive_comparison'
    linear, quadratic = [model['cross_validation']['log_magnitude_rmse'] for model in output['models']]
    if _number(linear) and _number(quadratic) and linear > 1e-12:
        output['quadratic_cv_reduction_fraction'] = 1-quadratic/linear
        if quadratic > 1e-12:
            output['cv_ratio_linear_over_quadratic'] = linear/quadratic
        else:
            output['cv_ratio_reason'] = 'quadratic_cv_residual_at_numerical_precision'
    else:
        output['cv_ratio_reason'] = 'cv_unavailable_or_linear_residual_at_numerical_precision'
    output['slope_meaning'] = 'For z=log(radius)-center, amplitude power is p(z)=linear_coefficient+2*quadratic_coefficient*z; the factor multiplying the displacement vector has power p(z)-1. Ranges apply only over observed radii.'
    def require_finite(value):
        if isinstance(value, dict):
            for item in value.values():
                require_finite(item)
        elif isinstance(value, list):
            for item in value:
                require_finite(item)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Radial curvature diagnostics produced nonfinite values')
    require_finite(output)
    return output
