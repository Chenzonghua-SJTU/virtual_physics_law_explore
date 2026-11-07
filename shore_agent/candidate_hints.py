"""Translate supplied observation diagnostics into bounded, untested DSL hints.

No observations are acquired, models fitted, files read, or laws selected here.
The complete diagnostic regression's errors are NOT errors of a pruned/shared
candidate. All hints require the ordinary fit and fresh-validation workflow.
"""
from __future__ import annotations

import math
from copy import deepcopy

from .expressions import Expression, ExpressionError, MAX_MAGNITUDE


CONTRIBUTION_FRACTION = .001
SHARED_COEFFICIENT_RELATIVE_TOLERANCE = .05
MAX_CANDIDATES = 3

_POWERS = {(('*'.join(f'{name}^{p}' if p != 1 else name
                    for name, p in (('x', i), ('y', total-i)) if p)) or '1'): (i, total-i)
           for total in range(4) for i in range(total, -1, -1)}


def _finite(value):
    try:
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value))
    except OverflowError:
        return False


def _stable(design):
    return (isinstance(design, dict) and design.get('full_column_rank') is True
            and design.get('coefficient_identifiability') == 'full_rank_design')


def _parameter(name, initial):
    # Use the DSL's existing default bounds, not a new physical constraint.
    return {'name': name, 'initial': float(initial)}


def _public_properties(task):
    names = task.get('allowed_properties', [])
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise ValueError('allowed_properties must be a list of strings')
    return sorted(set(names))


def _axis_terms(model):
    degree = model.get('degree')
    if type(degree) is not int or degree not in (1, 2, 3):
        return None
    expected = {term for term, powers in _POWERS.items() if sum(powers) <= degree}
    coefficients = model.get('diagnostic_coefficients')
    if not isinstance(coefficients, list) or len(coefficients) != len(expected):
        return None
    found, terms = set(), []
    for item in coefficients:
        if not isinstance(item, dict) or item.get('term') not in expected or item['term'] in found:
            return None
        found.add(item['term'])
        a, b, contribution = (item.get(key) for key in ('ax', 'ay', 'delta_velocity_contribution_rms'))
        if not all(_finite(value) for value in (a, b, contribution)) or contribution < 0:
            return None
        magnitude = math.hypot(a, b)
        if max(abs(a), abs(b)) > MAX_MAGNITUDE or (magnitude == 0 and contribution != 0):
            return None
        for axis, coefficient in (('ax', a), ('ay', b)):
            terms.append({'component': axis, 'term': item['term'],
                          'diagnostic_coefficient': float(coefficient),
                          'delta_velocity_contribution_rms': float(contribution * (abs(coefficient) / magnitude)) if magnitude else 0.})
    return terms


def _share_groups(terms):
    """Complete-link groups: same degree/sign; every pair within 5%.

    This is only a dimensionality-reduction hypothesis, never inferred symmetry.
    Comparing coefficients of unlike degree would compare unlike units.
    """
    groups = []
    for term in sorted(terms, key=lambda t: (sum(_POWERS[t['term']]),
                                            t['diagnostic_coefficient'], t['component'], t['term'])):
        value = term['diagnostic_coefficient']
        for group in groups:
            if all(sum(_POWERS[other['term']]) == sum(_POWERS[term['term']])
                   and (other['diagnostic_coefficient'] > 0) == (value > 0)
                   and abs(other['diagnostic_coefficient'] - value)
                       <= SHARED_COEFFICIENT_RELATIVE_TOLERANCE * max(abs(other['diagnostic_coefficient']), abs(value))
                   for other in group):
                group.append(term)
                break
        else:
            groups.append([term])
    return groups


def _spatial_candidate(model, allowed):
    cv = model.get('cross_validation', {})
    cv_errors = cv.get('errors') if isinstance(cv, dict) else None
    cv_error = cv_errors.get('relative_rmse') if isinstance(cv_errors, dict) else None
    if (not _stable(model.get('design')) or not isinstance(cv, dict) or cv.get('status') != 'available'
            or not _finite(cv_error) or cv_error < 0):
        return None, 'requires_stable_full_rank_coefficients_and_available_whole_probe_cv'
    terms = _axis_terms(model)
    if terms is None:
        return None, 'requires_complete_finite_monomial_coefficients_through_degree'
    maximum = max(term['delta_velocity_contribution_rms'] for term in terms)
    if maximum == 0:
        return None, 'no_nonzero_observed_increment_contribution'
    retained = [term for term in terms if term['delta_velocity_contribution_rms'] >= maximum * CONTRIBUTION_FRACTION]
    pruned = [term for term in terms if term['delta_velocity_contribution_rms'] < maximum * CONTRIBUTION_FRACTION]
    groups = [[term] for term in retained]
    shared = False
    if len(groups) > 5:
        groups = _share_groups(retained)
        shared = True
    if len(groups) > 5:
        return None, 'more_than_five_distinct_strong_coefficients_even_after_approximate_equal_groups'
    groups.sort(key=lambda group: min((term['component'], list(_POWERS).index(term['term'])) for term in group))
    expressions = {'ax': [], 'ay': []}
    parameters, group_evidence = [], []
    for i, group in enumerate(groups):
        name = f'c{i}'
        initial = math.fsum(term['diagnostic_coefficient'] / len(group) for term in group)
        parameters.append(_parameter(name, initial))
        for term in group:
            expression = term['term'].replace('^', '**')
            expressions[term['component']].append(name if expression == '1' else f'{name}*{expression}')
        group_evidence.append({'parameter': name, 'members': group,
                               'max_relative_deviation_from_initial': max(abs(term['diagnostic_coefficient']-initial) / abs(initial) for term in group)})
    law_spec = {axis: '+'.join(items) or '0' for axis, items in expressions.items()}
    warnings = [
        'This candidate has not been fitted or validated. Source CV describes the complete diagnostic regression BEFORE pruning or coefficient sharing.',
        'Small observed contributions can matter outside sampled trajectories; discarded terms are not proven absent.',
        'Spatial-only candidates omit time, velocity and property dependence. Their absence from this dictionary does not establish independence.',
        'Integral regression uses approximate numerical quadrature; its coefficients are initial guesses, not exact physical constants.'
    ]
    if shared:
        warnings.append('Approximate equal-coefficient groups are testable parameter-sharing hypotheses, not evidence of symmetry. Refitting may reject the constraint.')
    if allowed:
        warnings.append('Public property effects remain unresolved by spatial regression: ' + ', '.join(allowed) + '.')
    candidate = {
        'kind': 'approximate_shared_polynomial' if shared else 'independent_polynomial',
        'law_spec': law_spec, 'parameter_spec': parameters,
        'evidence': {'source_degree': model['degree'], 'source_whole_probe_cv_relative_rmse': float(cv_error),
                     'source_training_relative_rmse': (model.get('training_errors') or {}).get('relative_rmse'),
                     'pruning_rule': 'axis contribution < fraction * largest axis contribution',
                     'pruning_relative_fraction': CONTRIBUTION_FRACTION,
                     'largest_axis_delta_velocity_contribution_rms': maximum,
                     'pruned_axis_terms': pruned, 'coefficient_groups': group_evidence,
                     'sharing_pairwise_relative_tolerance': SHARED_COEFFICIENT_RELATIVE_TOLERANCE if shared else None,
                     'source_errors_are_not_candidate_errors': True},
        'warnings': warnings}
    return candidate, None


def _radial_candidate(radial, allowed, curvature):
    if (not isinstance(radial, dict) or radial.get('status') != 'empirical_fit'
            or radial.get('usable_for_power_interpretation') is not True or not _stable(radial.get('design'))
            or radial.get('radial_direction') not in ('inward', 'outward')
            or radial.get('reference_point') != [0., 0.]):
        return None, 'requires_stable_geometrically_screened_empirical_radial_fit_at_public_origin'
    power, intercept = radial.get('acceleration_magnitude_radius_power'), radial.get('intercept_log_magnitude')
    powers = radial.get('positive_property_powers')
    if (not all(_finite(value) for value in (power, intercept)) or not isinstance(powers, dict)
            or not all(name in allowed and _finite(value) for name, value in powers.items())
            or len(powers) > 3):
        return None, 'radial_coefficients_unavailable_or_exceed_parameter_limit'
    unknown = sorted(set(allowed) - set(powers))
    declared_unknown = radial.get('unidentified_property_controls', [])
    if (not isinstance(declared_unknown, list) or any(not isinstance(name, str) for name in declared_unknown)
            or set(powers).intersection(declared_unknown)):
        return None, 'property_power_conflicts_with_unidentified_controls'
    # A varying, unidentifiable control cannot safely be silently omitted.
    fixed = radial.get('conditional_on_fixed_property_values', {})
    if not isinstance(fixed, dict) or any(name not in fixed for name in unknown):
        return None, 'some_public_controls_are_neither_identified_nor_observed_fixed'
    if any(not isinstance(fixed[name], list) or len(fixed[name]) != 1
           or not _finite(fixed[name][0]) or fixed[name][0] <= 0 for name in unknown):
        return None, 'unidentified_control_does_not_have_one_positive_observed_fixed_value'
    try:
        amplitude = math.exp(intercept) * (-1. if radial['radial_direction'] == 'inward' else 1.)
    except OverflowError:
        return None, 'radial_amplitude_outside_finite_dsl_range'
    if amplitude == 0 or not _finite(amplitude) or abs(amplitude) > MAX_MAGNITUDE:
        return None, 'radial_amplitude_outside_finite_dsl_range'
    squared_radius_power = (power-1.) / 2.
    parameters = [_parameter('c0', amplitude), _parameter('c1', squared_radius_power)]
    factor = '(x**2+y**2)**c1'
    for i, name in enumerate(sorted(powers), 2):
        parameters.append(_parameter(f'c{i}', powers[name]))
        factor += f'*q({name!r})**c{i}'
    warnings = [
        'This empirical pure-power candidate has not been fitted or validated; geometry screening does not establish a good power-law fit.',
        'The coordinate origin is only a candidate center. Midpoint acceleration estimates and unmodeled time/velocity effects can bias slopes.',
        'This local power hypothesis may fail over other radii, at the origin, or with negative/zero property values. Check the formal domain and fresh trajectories.',
        'Property exponents are conditional empirical associations, not causal identification.'
    ]
    if unknown:
        warnings.append('Unvaried property effects are UNKNOWN, not zero: ' + ', '.join(unknown) + '. The amplitude is conditional on the listed observed fixed values.')
    evidence = {'source_log_magnitude_rmse': radial.get('log_magnitude_rmse'),
                'acceleration_magnitude_radius_power': float(power),
                'vector_factor_power': float(power-1.),
                'squared_radius_factor_power': float(squared_radius_power),
                'power_conversion': 'magnitude exponent p -> vector radius exponent p-1 -> squared-radius exponent (p-1)/2',
                'observed_radius_range': deepcopy(radial.get('radius_range')),
                'unknown_property_effects': unknown, 'conditional_on_fixed_property_values': {name: list(fixed[name]) for name in unknown},
                'source_errors_are_not_candidate_errors': True}
    if isinstance(curvature, dict) and curvature.get('status') == 'descriptive_comparison':
        evidence['source_curvature_cv_ratio_linear_over_quadratic'] = curvature.get('cv_ratio_linear_over_quadratic')
        warnings.append('Also compare the supplied log-radius curvature diagnostics: a single exponent cannot represent changing local slopes.')
    return {'kind': 'empirical_radial_power',
            'law_spec': {axis: f'c0*{coordinate}*{factor}' for axis, coordinate in (('ax', 'x'), ('ay', 'y'))},
            'parameter_spec': parameters, 'evidence': evidence, 'warnings': warnings}, None


def _signature(candidate):
    # Numbering is deterministic. Equal structure at different polynomial degrees
    # represents one hint, not three apparently independent confirmations.
    return tuple(candidate['law_spec'][axis] for axis in ('ax', 'ay'))


def propose_observation_candidates(diagnostics, public_task):
    """Return at most three untested hints from the supplied complete diagnostics.

    Inputs are never modified. Only public property names and supplied diagnostic
    fields are consumed; task/world identity and all unrelated fields are ignored.
    Named coefficients/exponents are checked by the ordinary DSL parser. No law
    record or official acceptance/score is created.
    """
    if not isinstance(diagnostics, dict) or not isinstance(public_task, dict):
        raise ValueError('diagnostics and public_task must be mappings')
    allowed = _public_properties(public_task)
    skipped, spatial = [], []
    for model in diagnostics.get('space_regression', {}).get('models', []):
        if not isinstance(model, dict):
            continue
        candidate, reason = _spatial_candidate(model, allowed)
        if candidate is None:
            skipped.append({'family': 'spatial_polynomial', 'degree': model.get('degree'), 'reason': reason})
        else:
            spatial.append(candidate)
    spatial.sort(key=lambda c: (max(c['evidence']['source_whole_probe_cv_relative_rmse'], 1e-10),
                                c['evidence']['source_degree'], len(c['parameter_spec'])))
    radial, reason = _radial_candidate(diagnostics.get('radial_diagnostic'), allowed, diagnostics.get('radial_curvature'))
    if radial is None:
        skipped.append({'family': 'empirical_radial_power', 'reason': reason})
    candidates, seen = [], set()
    for candidate in spatial:
        signature = _signature(candidate)
        if signature not in seen:
            seen.add(signature)
            candidates.append(candidate)
    candidates = candidates[:MAX_CANDIDATES - (radial is not None)] + ([radial] if radial is not None else [])
    legal = []
    for candidate in candidates:
        try:
            Expression(candidate['law_spec'], candidate['parameter_spec'], allowed_properties=allowed)
        except ExpressionError:
            skipped.append({'family': candidate['kind'], 'reason': 'candidate_exceeds_existing_dsl_constraints'})
        else:
            legal.append(candidate)
    return {'method_version': 'observation_candidate_hints_v1',
            'source': 'only supplied acquired-observation diagnostics and public property names',
            'candidates': legal, 'skipped_families': skipped,
            'meaning': 'Untested structural hints and initial guesses, not fitted laws or a choice of final answer. Use ordinary fit and fresh validation; no official score is inferred.',
            'ordering': 'Spatial hints ordered by full diagnostic whole-probe CV (values below 1e-10 tied), then degree. This does not evaluate the pruned/shared candidate. A screened radial alternative, if any, is also included.'}
