"""Compact model-facing SR decisions; full evidence remains in the run store."""
from __future__ import annotations

import copy


def _pick(mapping, keys):
    return {key: copy.deepcopy(mapping[key]) for key in keys if key in mapping}


def candidate_feedback(candidate):
    output = _pick(candidate, ('rank', 'law_spec', 'parameter_spec', 'fitted_parameters',
        'complexity', 'structural_complexity', 'fit_stage', 'trajectory_refit_status',
        'discovery_probe_ids', 'joint_fit_ready', 'prediction_accuracy_status'))
    residuals = candidate.get('residuals', {})
    output['residuals'] = _pick(residuals, ('acceleration_weighted_mse',))
    training = residuals.get('trajectory_training', {}).get('overall')
    if training is not None:
        output['residuals']['trajectory_training'] = _pick(training, ('position_rmse', 'velocity_rmse'))
    integral = residuals.get('observed_velocity_integral')
    if integral is not None:
        output['residuals']['observed_velocity_integral'] = _pick(integral, (
            'complete', 'relative_increment_rmse', 'domain_error_probe_ids',
            'denominator_sign_change_probe_ids'))
    output['independent_validation'] = False
    selection = candidate.get('selection_diagnostics')
    if selection is not None:
        output['selection'] = _pick(selection, ('metric', 'error', 'band_best_error',
            'absolute_tolerance', 'relative_mse_tolerance', 'observed_domain_or_pole_risk'))
    check = candidate.get('short_rollout_check')
    if check is not None:
        output['short_rollout_status'] = check.get('status', 'unknown')
    return output


def search_feedback(result):
    output = _pick(result, ('search_id', 'status', 'outcome', 'used_probe_ids',
        'discovery_probe_ids', 'feature_names', 'dropped_constant_features',
        'omitted_incomplete_properties', 'effective_time_budget_seconds', 'wall_seconds',
        'stop_reason', 'rejection_counts', 'input_coverage', 'warnings', 'body_positions_included'))
    output['candidates'] = [candidate_feedback(c) for c in result.get('candidates', [])]
    axes = result.get('axis_candidates', {})
    if not output['candidates']:
        output['axis_candidates'] = {axis: [_pick(c, ('component', 'source', 'law_spec',
            'parameter_spec', 'parameter_count', 'complexity', 'loss', 'discovery_probe_ids',
            'joint_fit_ready', 'parameter_budget_compatible')) for c in rows] for axis, rows in axes.items()}
    else:
        output['single_axis_alternatives_in_audit'] = {axis: len(rows) for axis, rows in axes.items()}
    output['audit_path'] = f"analyses/{result['search_id']}.json"
    output['ranking_rule'] = ('Prefer simpler complete laws within comparable-error bands; '
                              'material accuracy gains can justify complexity. Search residuals are discovery diagnostics.')
    output['next_step'] = ('Fit a complete candidate using its unchanged law_spec, parameter_spec and used_probe_ids; '
        'compare alternatives if needed, then validate on fresh probes. All reported errors are discovery errors. '
        'Read audit_path with read_file only if detailed diagnostics or single-axis alternatives are needed.')
    return output
