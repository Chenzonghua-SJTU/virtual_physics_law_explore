"""Problem-PDF score arithmetic for developer-only post-session evaluation.

This module has no simulator or Agent imports. It consumes already evaluated
position statistics and privately checked declarations, never discovery inputs.
"""
import math


FORMULA_VERSION = 'shore_pdf_1101'
CLAIM_FIELDS = ('dynamics_order', 'hidden_matter', 'time_dependence')


def finite_nonnegative(value):
    return (type(value) in (int, float) and math.isfinite(value) and value >= 0)


def problem_score(position_mse, reference_variance, submitted_claims, expected_claims,
                  energy_used, n_trajectories, *, candidate_failed=False,
                  truth_failed=False, unavailable_reason=None, energy_budget=100,
                  formula_version=FORMULA_VERSION):
    """Implement PDF page 7 exactly, without inventing a pass/fail threshold.

    Position errors are squared vector norms. V uses the global mean reference
    position across all trajectories and sample times. A candidate execution
    failure zeros P (and hence C), while an oracle failure yields no score.
    """
    if not finite_nonnegative(energy_budget) or energy_budget <= 0:
        raise ValueError('energy_budget must be positive and finite')
    submitted_claims = submitted_claims if isinstance(submitted_claims, dict) else {}
    expected_claims = expected_claims if isinstance(expected_claims, dict) else {}
    checks = []
    for field in CLAIM_FIELDS:
        actual, expected = submitted_claims.get(field), expected_claims.get(field)
        correct = (expected is not None and type(actual) is type(expected) and actual == expected)
        checks.append({'field': field, 'submitted': actual, 'expected': expected,
                       'correct': correct, 'points': 5 if correct else 0})
    law = sum(check['points'] for check in checks) if all(field in expected_claims for field in CLAIM_FIELDS) else None
    result = {'status': 'unavailable', 'total': None, 'maximum': 100,
              'prediction': None, 'law': law, 'conservation': None,
              'position_mse': float(position_mse) if finite_nonnegative(position_mse) else None,
              'reference_variance': float(reference_variance) if finite_nonnegative(reference_variance) else None,
              'normalized_error': None,
              'energy_used': float(energy_used) if finite_nonnegative(energy_used) and energy_used <= energy_budget else None,
              'energy_budget': energy_budget,
              'claim_checks': checks, 'reason': unavailable_reason, 'formula_version': formula_version,
              'local_only': True, 'official_score': False,
              'source_note': (
                  'Uses the displayed PDF formula P=80/(1+10e). The nearby numeric examples '
                  'correspond to 5e and conflict with that formula; this implementation uses 10e '
                  'and applies the P>=40 conservation gate before display rounding.')}
    if unavailable_reason:
        return result
    if truth_failed:
        result['reason'] = 'truth_reference_failed'
        return result
    if type(n_trajectories) is not int or n_trajectories < 20:
        result['reason'] = 'fewer_than_20_test_trajectories'
        return result
    if law is None:
        result['reason'] = 'truth_claims_unavailable'
        return result
    if candidate_failed:
        result.update(status='scored', prediction=0.0, conservation=0.0,
                      total=float(law), reason='candidate_prediction_invalid')
        return result
    if result['position_mse'] is None or result['reference_variance'] is None:
        result['reason'] = 'invalid_position_statistics'
        return result
    error = result['position_mse'] / max(result['reference_variance'], 1e-12)
    if not math.isfinite(error):
        # Huge but finite position errors still approach a prediction score of
        # zero; keep JSON finite rather than persisting an Infinity sentinel.
        prediction = 0.0
    else:
        result['normalized_error'] = error
        prediction = 80.0 / (1.0 + 10.0 * error)
    result['prediction'] = prediction
    if prediction < 40.0:
        conservation = 0.0
    elif result['energy_used'] is None:
        result['reason'] = 'energy_usage_unavailable'
        return result
    else:
        conservation = 5.0 * (1.0 - result['energy_used'] / energy_budget)
    result.update(status='scored', conservation=conservation,
                  total=prediction + law + conservation, reason=None)
    return result
