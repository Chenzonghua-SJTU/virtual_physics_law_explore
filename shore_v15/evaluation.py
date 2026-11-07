"""Post-session v15 catalog evaluation of the unchanged local Agent's DSL.

The six public fixed suites replace the legacy random initial conditions.
Truth uses the vendored starter simulator; candidate integration remains the
local Agent's existing DOP853 implementation. This is not a contest submission
or a claim to use the contest law.py interface. Scoring follows the archived
ruleset and actual mission energy limit, without rewriting older E3 records.
"""
from __future__ import annotations

import numpy as np

from shore_agent.numerics import errors_for_rollouts, rollout as candidate_rollout
from shore_scoring import problem_score
from shore_rules import initial_energy, rules_for


def _visible_positions(simulator, maximum_time):
    """Supply clean grid background to candidate laws after session end only."""
    from .source import DT, rollout

    initial = simulator.background_initial_state()
    if len(initial['ids']) == 1:
        return lambda _t: initial['positions'].copy()
    history = None

    def positions(t):
        nonlocal history
        # Most candidates do not reference bodies; defer this truth rollout
        # until the numerical adapter actually requests visible state.
        if history is None:
            history = rollout(simulator._background_acceleration,
                              initial['positions'], initial['velocities'],
                              t_launch=0., duration=maximum_time)['positions']
        tick = float(t) / DT
        if tick < -1e-7 or tick > len(history) - 1 + 1e-7:
            raise ValueError('Evaluation background time is outside the fixed suite')
        tick = min(max(tick, 0.), len(history) - 1.)
        left = int(np.floor(tick))
        right = min(left + 1, len(history) - 1)
        fraction = tick - left
        return history[left] * (1. - fraction) + history[right] * fraction

    return positions


def evaluate_submission(run_dir, submission, law, environment, *, seed, requested_n_probes):
    """Called only after evaluate.py checks accepted status and archive identity."""
    from evaluate import _energy_used, _reference_variance, _read
    from .source import DevelopmentSimulator, NUMERICS_VERSION, agent_properties, catalog

    world_id = environment['world_id']
    world = world_id.removeprefix('world_')
    simulator = DevelopmentSimulator(world)
    cases = catalog.validation_cases(world)
    count = sum(len(case['probes']) for case in cases)
    maximum_time = max(case['t_launch'] + case['readout'][-1] for case in cases)
    visible_input = _visible_positions(simulator, maximum_time)
    probes, predictions, failures, initial_conditions, reference_positions = [], [], [], [], []
    for case in cases:
        specifications = []
        for index, source_probe in enumerate(case['probes']):
            properties = agent_properties(world, case['source_properties'], source_probe['properties'])
            initial = {'r0': source_probe['pos'], 'v0': source_probe['vel'],
                       't0': case['t_launch'], 'dt': case['readout'][0],
                       'properties': properties}
            probe_id = f"v15_{case['name']}_{index + 1}"
            initial_conditions.append({'probe_id': probe_id, 'case': case['name'],
                                       'n_samples': len(case['readout']),
                                       'readout': case['readout'], **initial})
            specifications.append((probe_id, initial))
        try:
            truth = simulator.launch(case['probes'], case['t_launch'], case['readout'],
                                     source_properties=case['source_properties'])
        except (ValueError, OverflowError, FloatingPointError) as exc:
            failures.extend({'probe_id': probe_id, 'stage': 'truth_reference', 'reason': str(exc)}
                            for probe_id, _initial in specifications)
            continue
        for index, (probe_id, initial) in enumerate(specifications):
            positions, velocities = truth['positions'][:, index], truth['velocities'][:, index]
            reference_positions.append(positions)
            probe = {'probe_id': probe_id, 'initial_conditions': initial,
                     'times': truth['times'].tolist(), 'r_obs': positions.tolist(),
                     'v_obs': velocities.tolist()}
            try:
                prediction = candidate_rollout(law['law_spec'], law['fitted_parameters'], probe, visible_input)
                probes.append(probe)
                predictions.append(prediction)
            except (ValueError, OverflowError, FloatingPointError) as exc:
                failures.append({'probe_id': probe_id, 'stage': 'candidate_rollout', 'reason': str(exc)})
    metrics = errors_for_rollouts(probes, predictions) if probes else None
    truth_failed = any(item['stage'] == 'truth_reference' for item in failures)
    variance = None
    if not truth_failed:
        try:
            variance = _reference_variance(reference_positions)
        except (ValueError, OverflowError, FloatingPointError):
            truth_failed = True
    mse = None
    if not failures:
        mse = float(np.mean(np.concatenate([
            np.sum((np.asarray(prediction['r_pred']) - np.asarray(probe['r_obs'])) ** 2, axis=1)
            for probe, prediction in zip(probes, predictions)])))
    used, energy_source = _energy_used(run_dir, submission)
    rules = rules_for(environment)
    energy_budget = initial_energy(_read(run_dir / 'mission.json'), environment)
    score = problem_score(mse, variance, submission.get('claims'), simulator.claims_truth,
                          used, count, truth_failed=truth_failed,
                          candidate_failed=any(item['stage'] == 'candidate_rollout' for item in failures),
                          energy_budget=energy_budget, formula_version=rules['score_formula_version'])
    score.update(source='v15_public_catalog_local_agent_evaluation', energy_source=energy_source,
                 energy_budget=energy_budget,
                 source_note='Local discovery score: P=80/(1+10e), three declarations worth 5 each; '
                             f'C=5*(1-E/{energy_budget:g}) only when P>=40. '
                             f"Ruleset={rules['ruleset']}; this remains a local compatibility evaluation.")
    return {
        'evaluation_kind': 'independent_post_session_public_v15_catalog',
        'evaluation_protocol': 'v15_fixed_cases_local_dsl_dop853',
        'local_only': True, 'official_score': False, 'world_set': 'v15', 'world_id': world_id,
        'ruleset': rules['ruleset'],
        'physics_version': environment['physics_version'],
        'catalog_version': catalog.VERSION, 'truth_numerics_version': NUMERICS_VERSION,
        'body_input_protocol': 'clean_v15_grid_background_linear_interpolation',
        'body_input_note': 'After session end, clean visible background is sampled on the v15 0.005 '
                           'grid and linearly interpolated for the unchanged candidate integrator. '
                           'These evaluator inputs never return to the exploring Agent.',
        'truth_reference': 'Unmodified v15 DevelopmentSimulator and fixed public validation cases; no noise',
        'evaluation_noise': False, 'exploration_noise': bool(environment.get('noise')),
        'submission_id': submission['submission_id'], 'law_id': law['law_id'],
        'claims': submission['claims'], 'seed': seed, 'seed_used': False,
        'requested_n_probes': requested_n_probes,
        'n_trajectories': count, 'n_successful': len(predictions), 'complete': not failures and not truth_failed,
        'overall': metrics['overall'] if metrics and not failures and not truth_failed else None,
        'successful_subset_overall': metrics['overall'] if metrics else None,
        'per_probe': metrics['per_probe'] if metrics else [], 'failures': failures,
        'initial_conditions': initial_conditions, 'n_cases': len(cases),
        'test_set_policy': 'All fixed v15 catalog cases; seed and n_probes do not select or truncate the suite',
        'score': score,
        'interpretation': 'Local adapter validation, not an official contest result. Truth uses the '
                          'starter fixed integrator; candidate prediction uses the existing local '
                          'Agent integrator and DSL with the mass/charge property bridge.',
    }
