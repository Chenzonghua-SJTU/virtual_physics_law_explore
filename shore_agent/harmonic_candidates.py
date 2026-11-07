"""Unfitted bounded DSL hypotheses from supplied harmonic diagnostics only."""
from __future__ import annotations

import copy
import math

from .candidate_hints import CONTRIBUTION_FRACTION, SHARED_COEFFICIENT_RELATIVE_TOLERANCE
from .expressions import Expression


TERMS = ('1', 'x', 'y', 'sin(omega*t)', 'x*sin(omega*t)', 'y*sin(omega*t)',
         'cos(omega*t)', 'x*cos(omega*t)', 'y*cos(omega*t)')


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _degree(term):
    return int(term in ('x', 'y') or term.startswith(('x*', 'y*')))


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _resolved(value):
    value = _mapping(value)
    return (value.get('status') == 'locally_resolved_within_searched_family'
            and value.get('reasons') == [])


def propose_harmonic_candidate(diagnostic, public_task):
    """Return one unfit hint or a reason; never choose, fit or submit a law.

    Signed coefficient sharing compares only equal spatial degree, preserving
    coefficient dimensions because sine and cosine are dimensionless. It is a
    dimensionality-reduction hypothesis, not an inferred physical symmetry.
    """
    def unavailable(reason):
        return {'candidate': None, 'reason': reason}

    if not isinstance(diagnostic, dict) or diagnostic.get('status') != 'descriptive_comparison':
        return unavailable('requires_completed_harmonic_comparison')
    if not isinstance(public_task, dict):
        return unavailable('requires_public_task_mapping')
    model = _mapping(diagnostic.get('harmonic_model'))
    design, cv = _mapping(model.get('design')), _mapping(model.get('cross_validation'))
    omega = model.get('omega')
    if (design.get('full_column_rank') is not True
            or design.get('coefficient_identifiability') != 'full_rank_design'
            or not _resolved(model.get('frequency_identification'))
            or cv.get('status') != 'available' or cv.get('frequency_identification_in_all_folds') is not True
            or not _number(omega) or omega <= 0):
        return unavailable('requires_stable_design_and_resolved_frequency_in_full_data_and_all_cv_folds')
    folds = cv.get('folds')
    if (cv.get('split_unit') != 'whole_probe_trajectory'
            or not isinstance(folds, list) or len(folds) < 2
            or any(not isinstance(fold, dict) or fold.get('usable') is not True
                   or not _resolved(fold.get('frequency_identification'))
                   or not _number(fold.get('selected_omega')) or fold['selected_omega'] <= 0
                   for fold in folds)):
        return unavailable('requires_complete_resolved_whole_probe_cv_folds')
    cv_error = _mapping(cv.get('errors')).get('relative_rmse')
    if not _number(cv_error) or cv_error < 0:
        return unavailable('requires_finite_whole_probe_reconstruction_cv')
    coefficients = model.get('diagnostic_coefficients')
    if (not isinstance(coefficients, list) or len(coefficients) != len(TERMS)
            or any(not isinstance(item, dict) or not isinstance(item.get('term'), str) for item in coefficients)
            or {item.get('term') for item in coefficients} != set(TERMS)):
        return unavailable('requires_complete_independent_affine_harmonic_coefficients')
    terms = []
    for item in coefficients:
        a, b, contribution = (item.get(key) for key in ('ax', 'ay', 'delta_velocity_contribution_rms'))
        if not all(_number(value) for value in (a, b, contribution)) or contribution < 0:
            return unavailable('requires_finite_coefficients_and_nonnegative_contributions')
        magnitude = math.hypot(a, b)
        if not _number(magnitude):
            return unavailable('requires_finite_coefficient_vector_magnitudes')
        if magnitude == 0 and contribution != 0:
            return unavailable('inconsistent_zero_coefficient_contribution')
        for axis, value in (('ax', a), ('ay', b)):
            terms.append({'axis': axis, 'term': item['term'], 'coefficient': value,
                          'contribution': contribution * (abs(value) / magnitude) if magnitude else 0.})
    maximum = max(term['contribution'] for term in terms)
    if maximum <= 0:
        return unavailable('no_nonzero_observed_contribution')
    kept = [term for term in terms if term['contribution'] > 0
            and term['contribution'] >= CONTRIBUTION_FRACTION * maximum]
    if not any('omega' in term['term'] for term in kept):
        return unavailable('no_retained_harmonic_contribution')
    groups = [[term] for term in kept]
    shared = len(groups) > 4
    if shared:
        groups = []
        for term in sorted(kept, key=lambda t: (_degree(t['term']), abs(t['coefficient']), t['axis'], t['term'])):
            for group in groups:
                if all(_degree(other['term']) == _degree(term['term'])
                       and abs(abs(other['coefficient'])-abs(term['coefficient'])) <=
                       SHARED_COEFFICIENT_RELATIVE_TOLERANCE * max(abs(other['coefficient']), abs(term['coefficient']))
                       for other in group):
                    group.append(term)
                    break
            else:
                groups.append([term])
    if len(groups) > 4:
        return unavailable('more_than_four_distinct_amplitudes_plus_free_frequency')
    groups.sort(key=lambda group: min((term['axis'], TERMS.index(term['term'])) for term in group))
    frequency_name = 'c' + str(len(groups))
    parameters, expressions = [], {'ax': [], 'ay': []}
    evidence = []
    for index, group in enumerate(groups):
        name = f'c{index}'
        if shared:
            scale = max(abs(term['coefficient']) for term in group)
            initial = scale * (math.fsum(abs(term['coefficient']) / scale for term in group) / len(group))
        else:
            initial = group[0]['coefficient']
        parameters.append({'name': name, 'initial': initial})
        for term in group:
            sign = '-' if shared and term['coefficient'] < 0 else '+'
            factor = term['term'].replace('omega', frequency_name)
            expression = name if factor == '1' else name + '*' + factor
            expressions[term['axis']].append(sign + expression)
        evidence.append({'parameter': name, 'members': group,
                         'spatial_degree': _degree(group[0]['term']),
                         'coefficient_dimensions': ('length/time^2' if _degree(group[0]['term']) == 0 else '1/time^2'),
                         'max_relative_magnitude_deviation': max(abs(abs(t['coefficient'])-abs(initial))/abs(initial) for t in group)})
    search = _mapping(model.get('frequency_search'))
    lower, upper = search.get('frequency_lower'), search.get('frequency_upper')
    if (search.get('grid_capped') is True
            or not all(_number(value) for value in (lower, upper)) or not 0 < lower <= omega <= upper):
        return unavailable('requires_valid_data_derived_frequency_search_bounds')
    parameters.append({'name': frequency_name, 'initial': omega, 'lower': lower, 'upper': upper})
    law_spec = {axis: (''.join(items).lstrip('+') or '0') for axis, items in expressions.items()}
    allowed = public_task.get('allowed_properties', [])
    try:
        Expression(law_spec, parameters, allowed_properties=allowed)
    except (TypeError, ValueError):
        return unavailable('candidate_failed_ordinary_dsl_validation')
    return {'candidate': {
        'kind': 'signed_shared_affine_harmonic' if shared else 'independent_affine_harmonic',
        'law_spec': law_spec, 'parameter_spec': parameters,
        'evidence': {'source_whole_probe_cv_relative_rmse': cv_error,
                     'source_errors_are_not_candidate_errors': True,
                     'candidate_cross_validation': {'status': 'unavailable',
                         'reason': 'pruned_or_shared_hypothesis_has_not_been_fitted_or_validated'},
                     'coefficient_groups': evidence,
                     'pruned_axis_terms': [term for term in terms if term not in kept],
                     'pruning_relative_fraction': CONTRIBUTION_FRACTION,
                     'sharing_pairwise_relative_tolerance': SHARED_COEFFICIENT_RELATIVE_TOLERANCE if shared else None,
                     'source_frequency_identification': copy.deepcopy(model['frequency_identification'])},
        'warnings': [
            'Unfitted hypothesis only: full-regression CV does not validate this pruned/shared candidate. Use ordinary trajectory fitting and fresh validation.',
            'Pruning uses acquired-trajectory contributions only; a small omitted term may dominate outside those observations.',
            'Opposite-sign approximate coefficient sharing is a testable parameter constraint, not proven symmetry or a conserved quantity.',
            'Frequency bounds describe the acquired-data search band, not physical truth. Aliases outside/between searched frequencies remain possible.',
            'Public properties, velocity and observed moving sources are omitted, not proven irrelevant. Harmonic time terms alone do not establish explicit physical time dependence.',
        ],
    }, 'reason': None}
