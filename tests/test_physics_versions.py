"""Versioned truth is private test data, never supplied to a discovery model."""
import json

import pytest

from evaluate import _evaluation_environment, evaluate_run
from shore_sim.simulator import Simulator
from shore_worlds import CURRENT_PHYSICS_VERSION, LEGACY_PHYSICS_VERSION, PHYSICS_VERSIONS


def write_archive(root, world_id, *, config_version=None, mission_version=None,
                  include_mission=True, law=None):
    environment = {'world_id': world_id, 'time_max': 2, 'position_limit': 3, 'velocity_limit': 2}
    if config_version is not None:
        environment['physics_version'] = config_version
    (root / 'config.json').write_text(json.dumps({'environment': environment}))
    if include_mission:
        task = {'world_id': world_id}
        if mission_version is not None:
            task['physics_version'] = mission_version
        (root / 'mission.json').write_text(json.dumps({'task': task}))
    (root / 'records/submission').mkdir(parents=True)
    (root / 'records/law').mkdir()
    submission = {'submission_id': 's1', 'law_id': 'law_1', 'status': 'accepted', 'session_ended': True,
                  'claims': {'dynamics_order': 2, 'hidden_matter': False, 'time_dependence': False}}
    (root / 'records/submission/s1.json').write_text(json.dumps(submission))
    record = {'law_id': 'law_1', 'law_spec': {'ax': '0', 'ay': '0'},
              'fitted_parameters': {}, 'known_bodies': []}
    record.update(law or {})
    (root / 'records/law/law_1.json').write_text(json.dumps(record))


@pytest.mark.parametrize('world_id', ['world_3', 'world_5'])
@pytest.mark.parametrize('version', PHYSICS_VERSIONS)
def test_evaluation_uses_archived_physics_without_rewriting_records(tmp_path, world_id, version):
    bodies = [{'body_id': name, 'position': point} for name, point in
              [('b1', [-2, 0]), ('b2', [2, 0]), ('b3', [0, 3])]]
    if version == LEGACY_PHYSICS_VERSION:
        if world_id == 'world_3':
            spec = {'ax': '-k*x-g*x**3', 'ay': '-k*(y-c)-g*(y-c)**3'}
            params = {'k': .2, 'g': .015, 'c': 1.}
        else:
            spec = {'ax': '-k*x+w*vy', 'ay': '-k*(y-c)-w*vx'}
            params = {'k': .3, 'w': .45, 'c': 1.}
        # Existing historical files have no version marker at all.
        write_archive(tmp_path, world_id, law={'law_spec': spec, 'fitted_parameters': params})
    else:
        if world_id == 'world_3':
            spec = {'ax': 'sum_b((k+g*((bx-x)**2+(by-y)**2))*(bx-x))',
                    'ay': 'sum_b((k+g*((bx-x)**2+(by-y)**2))*(by-y))'}
            params = {'k': .06, 'g': .004}
        else:
            spec = {'ax': 'sum_b(k*(bx-x)+g*vy/((bx-x)**2+(by-y)**2+s))',
                    'ay': 'sum_b(k*(by-y)-g*vx/((bx-x)**2+(by-y)**2+s))'}
            params = {'k': .1, 'g': 1.2, 's': 4.} if version == 'v2' else {'k': .1, 'g': 1., 's': 1.}
        write_archive(tmp_path, world_id, config_version=version, mission_version=version,
                      law={'law_spec': spec, 'fitted_parameters': params, 'known_bodies': bodies})
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*.json')}
    result = evaluate_run(tmp_path, n_probes=2)
    assert result['physics_version'] == version
    assert result['complete'] and result['n_successful'] == 2
    assert result['overall']['position_rmse'] < 1e-5
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*.json')} == before
    if world_id == 'world_5':
        assert ('matrix-exponential' if version == LEGACY_PHYSICS_VERSION else 'Radau') in result['truth_reference']


@pytest.mark.parametrize('config_version,mission_version,include_mission,expected', [
    (None, None, True, LEGACY_PHYSICS_VERSION),
    (None, None, False, LEGACY_PHYSICS_VERSION),
    (LEGACY_PHYSICS_VERSION, None, True, LEGACY_PHYSICS_VERSION),
] + [(None, version, True, version) for version in PHYSICS_VERSIONS]
  + [(version, version, True, version) for version in PHYSICS_VERSIONS]
  + [(version, None, False, version) for version in PHYSICS_VERSIONS])
def test_version_resolution_from_config_and_mission(tmp_path, config_version, mission_version,
                                                  include_mission, expected):
    write_archive(tmp_path, 'world_3', config_version=config_version, mission_version=mission_version,
                  include_mission=include_mission)
    environment, world_id = _evaluation_environment(tmp_path)
    assert world_id == 'world_3' and environment['physics_version'] == expected


@pytest.mark.parametrize('config_version,mission_version', [
    ('v2', None), ('v3', None),
    ('unknown', None), (None, 'unknown'),
] + [(config, mission) for config in PHYSICS_VERSIONS for mission in PHYSICS_VERSIONS
     if config != mission])
def test_version_mismatch_or_unknown_is_rejected_before_truth_access(tmp_path, monkeypatch,
                                                                   config_version, mission_version):
    import shore_sim.simulator as simulator
    write_archive(tmp_path, 'world_5', config_version=config_version, mission_version=mission_version)
    monkeypatch.setattr(simulator, 'truth_trajectory', lambda *a, **k: pytest.fail('Oracle must not run'))
    with pytest.raises(ValueError, match='version'):
        evaluate_run(tmp_path, n_probes=1)


@pytest.mark.parametrize('version', [None, *PHYSICS_VERSIONS])
def test_simulator_pins_selected_version_for_mission_and_dynamics(version):
    config = {'world_id': 'world_5', 'noise': False}
    if version is not None:
        config['physics_version'] = version
    expected = version or CURRENT_PHYSICS_VERSION
    simulator = Simulator(config)
    assert simulator.config['physics_version'] == expected
    mission = simulator.request('mission')['data']
    assert mission['task']['physics_version'] == expected
    parameters = {'probes': [{'r0': [1, 2], 'v0': [.5, -.2], 'properties': {}}],
                  't0': 0, 'dt': .1, 'n_samples': 5}
    before = simulator.request('insert_probe', **parameters)['data']['probes'][0]
    simulator.config['physics_version'] = 'v2' if expected != 'v2' else 'v3'
    after = simulator.request('insert_probe', **parameters)['data']['probes'][0]
    assert before['v_obs'] == after['v_obs']
    assert simulator.request('mission')['data'] == mission


@pytest.mark.parametrize('value', [None, '', 'unknown', 'v5', True, 2, []])
def test_simulator_rejects_unknown_physics_version(value):
    with pytest.raises(ValueError, match='invalid_physics_version'):
        Simulator({'physics_version': value})
