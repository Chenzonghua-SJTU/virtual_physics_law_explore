import copy

import pytest

from shore_rules import apply_model_rules, apply_rules, initial_energy, rules_for


def test_e3_configs_remain_unchanged_and_mission_limits_are_authoritative():
    config = {'environment': {'wall_seconds': 3600, 'noise': False},
              'model': {'thinking': True, 'max_tokens_per_call': 65536}}
    original = copy.deepcopy(config)
    assert apply_rules(config) == original
    assert initial_energy() == 100
    assert initial_energy({'task': {'limits': {'initial_energy': 10}}}) == 10
    assert initial_energy({'data': {'task': {'limits': {'energy_budget': 10}}}}) == 10
    assert config == original


def test_e4_enforces_profile_after_old_config_merge_without_mutating_input():
    config = {'environment': {'ruleset': 'e4', 'wall_seconds': 3600, 'energy_budget': 100, 'noise': False},
              'model': {'thinking': True, 'max_tokens_per_call': 65536}}
    effective = apply_rules(config)
    assert effective['environment'] == {'ruleset': 'e4', 'wall_seconds': 300, 'energy_budget': 10, 'noise': True}
    assert effective['model'] == {'ruleset': 'e4', 'thinking': False, 'max_tokens_per_call': 4096}
    assert config['environment']['energy_budget'] == 100
    assert rules_for('e4')['score_formula_version'] != rules_for()['score_formula_version']
    config['model']['max_tokens_per_call'] = 2048
    assert apply_rules(config)['model']['max_tokens_per_call'] == 2048


def test_e4_cannot_be_applied_to_the_legacy_physical_backend():
    with pytest.raises(ValueError, match='e4_requires_v15'):
        apply_rules({'environment': {'ruleset': 'e4', 'world_set': 'legacy'}})


def test_e5_keeps_timed_limits_and_score_formula_while_disabling_observation_noise():
    config = {'environment': {'ruleset': 'e5', 'noise': True, 'energy_budget': 100, 'wall_seconds': 3600},
              'model': {'thinking': True, 'max_tokens_per_call': 65536}}
    effective = apply_rules(config)
    assert effective['environment'] == {'ruleset': 'e5', 'noise': False, 'energy_budget': 10, 'wall_seconds': 300}
    assert effective['model'] == {'ruleset': 'e5', 'thinking': False, 'max_tokens_per_call': 4096}
    assert config['environment']['noise'] is True
    assert rules_for('e5')['score_formula_version'] == rules_for('e4')['score_formula_version']
    assert initial_energy(environment={'ruleset': 'e5'}) == 10
    assert apply_model_rules({'ruleset': 'e5', 'max_tokens_per_call': 2048})['max_tokens_per_call'] == 2048
    with pytest.raises(ValueError, match='e5_requires_v15'):
        apply_rules({'environment': {'ruleset': 'e5', 'world_set': 'legacy'}})


@pytest.mark.parametrize('name', ['E4', 'unknown', None, 0])
def test_unknown_explicit_profiles_are_rejected(name):
    with pytest.raises(ValueError, match='unknown_ruleset'):
        rules_for({'ruleset': name})
