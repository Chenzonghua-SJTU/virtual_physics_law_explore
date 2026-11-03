"""Private checks of source mechanisms and preservation of historical physics."""
import numpy as np
import pytest

from shore_sim import worlds
from shore_worlds import LEGACY_PHYSICS_VERSION, PHYSICS_VERSIONS, WORLD_IDS


@pytest.mark.parametrize('world_id,version',
                         [(world, version) for world in WORLD_IDS[:5] for version in ('v2', 'v3')]
                         + [(world, 'v4') for world in WORLD_IDS])
def test_new_physics_superposes_individual_sources_and_translates_with_them(monkeypatch, world_id, version):
    positions = np.array([[-2., 0.], [2., 0.], [0., 3.]])
    state = np.array([1.3, -1.7, .4, -.6])
    monkeypatch.setattr(worlds, '_BODIES', positions)
    together = worlds.acceleration(world_id, 0, state, physics_version=version)
    separate = []
    for position in positions:
        monkeypatch.setattr(worlds, '_BODIES', position[None, :])
        separate.append(worlds.acceleration(world_id, 0, state, physics_version=version))
        # A source at rest relative to a stationary probe has no self force.
        np.testing.assert_array_equal(worlds.acceleration(world_id, 0, np.r_[position, [0., 0.]],
                                                         physics_version=version), [0, 0])
    np.testing.assert_allclose(together, np.sum(separate, axis=0), rtol=1e-14, atol=1e-14)
    shift = np.array([7.25, -3.75])
    monkeypatch.setattr(worlds, '_BODIES', positions + shift)
    translated = np.r_[state[:2] + shift, state[2:]]
    np.testing.assert_allclose(worlds.acceleration(world_id, 0, translated, physics_version=version),
                               together, rtol=1e-14, atol=1e-14)


@pytest.mark.parametrize('world_id', ['world_1', 'world_2', 'world_4'])
@pytest.mark.parametrize('version', PHYSICS_VERSIONS)
def test_unchanged_worlds_match_old_force_on_existing_layout(world_id, version):
    for state in np.random.default_rng(42).uniform(-5, 5, (30, 4)):
        current = worlds.acceleration(world_id, 0, state, physics_version=version)
        legacy = worlds.acceleration(world_id, 0, state, physics_version=LEGACY_PHYSICS_VERSION)
        np.testing.assert_allclose(current, legacy, rtol=1e-14, atol=1e-14)


@pytest.mark.parametrize('world_id', WORLD_IDS[:4])
def test_v3_retains_v2_force_exactly_in_other_worlds(world_id):
    for state in np.random.default_rng(43).uniform(-5, 5, (30, 4)):
        np.testing.assert_array_equal(
            worlds.acceleration(world_id, 0, state, physics_version='v3'),
            worlds.acceleration(world_id, 0, state, physics_version='v2'))


@pytest.mark.parametrize('version,expected', [
    ('v1', [.9, -.15]), ('v2', [51/65, -6/65]), ('v3', [1., -.2]), ('v4', [1., -.2]),
])
def test_world5_versions_keep_fixed_acceleration_regressions(version, expected):
    # At the origin, source squared distances are 4, 4, 9. With v=(1,2),
    # the v2 transverse coefficient is 51/130 and the v3 coefficient is 1/2.
    np.testing.assert_allclose(worlds.acceleration('world_5', 0, [0, 0, 1, 2],
                                                 physics_version=version),
                               expected, rtol=0, atol=2e-15)


@pytest.mark.parametrize('world_id,expected', [('world_3', [-.32116, .558915]),
                                               ('world_5', [-.6, .315])])
def test_legacy_changed_worlds_retain_their_original_fields(world_id, expected):
    state = [1.4, -1.1, .7, -.4]
    legacy = worlds.acceleration(world_id, 0, state, physics_version=LEGACY_PHYSICS_VERSION)
    np.testing.assert_allclose(legacy, expected, rtol=0, atol=2e-15)
    assert not np.allclose(worlds.acceleration(world_id, 0, state), legacy)


@pytest.mark.parametrize('version', ['v2', 'v3', 'v4'])
def test_world5_source_deflection_decays_with_distance_and_does_no_work(monkeypatch, version):
    monkeypatch.setattr(worlds, '_BODIES', np.array([[0., 0.]]))
    velocity = np.array([.7, -.4])
    magnitudes = []
    for position in ([0., 0.], [1., 0.], [4., 0.]):
        moving = worlds.acceleration('world_5', 0, np.r_[position, velocity], physics_version=version)
        stationary = worlds.acceleration('world_5', 0, np.r_[position, [0., 0.]], physics_version=version)
        deflection = moving - stationary
        assert abs(np.dot(velocity, deflection)) < 1e-14
        magnitudes.append(np.linalg.norm(deflection))
    assert magnitudes[0] > magnitudes[1] > magnitudes[2] > 0


@pytest.mark.parametrize('world_id', ['world_3', 'world_4', 'world_5'])
@pytest.mark.parametrize('version', PHYSICS_VERSIONS)
def test_independent_oracle_does_not_call_simulator_force(monkeypatch, world_id, version):
    def fail(*args, **kwargs):
        raise AssertionError('oracle reused simulated force')
    monkeypatch.setattr(worlds, 'acceleration', fail)
    states = worlds.truth_trajectory([1, -1], [.4, -.3], [0, .1, .2], world_id=world_id,
                                     physics_version=version)
    assert states.shape == (3, 4) and np.isfinite(states).all()
