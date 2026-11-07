import numpy as np

from shore_agent.symbolic_geometry import feature_table, expand_aliases, radial_projection
from shore_agent.symbolic_regression import export_candidate
from shore_agent.expressions import Expression


def dataset(acceleration=None):
    angle = np.linspace(0, 2*np.pi, 12, endpoint=False)
    radius = np.linspace(1, 3, 12)
    position = radius[:, None]*np.column_stack((np.cos(angle), np.sin(angle)))
    states = np.column_stack((np.arange(12), position, position[:, ::-1]))
    return dict(states=states, X=states[:, 1:], feature_names=['x','y','vx','vy'],
                y=-position if acceleration is None else acceleration,
                weights=np.ones(12)/12)


def test_alias_expansion_matches_state_geometry_and_is_exportable():
    data = dataset()
    table, names = feature_table(data)
    np.testing.assert_allclose(table[:, names.index('radius2')], np.sum(data['states'][:, 1:3]**2, axis=1))
    formula = export_candidate(expand_aliases('x/radius2'), expand_aliases('y/radius2'), data['feature_names'])
    expression = Expression(formula['law_spec'], formula['parameter_spec'])
    np.testing.assert_allclose(expression.acceleration(0, (3,4), (0,0), [], {}, {}), [.12,.16])
    assert 'radius' not in str(formula)


def test_empty_or_constant_coordinates_are_not_reintroduced():
    data = dataset()
    data.update(X=np.empty((12,0)), feature_names=[])
    table, names = feature_table(data)
    assert table.shape == (12,0) and names == []
    projected, diagnostics = radial_projection(data)
    assert projected is None and diagnostics['reason'] == 'both_coordinate_features_required'


def test_projection_requires_both_collinearity_and_direction_coverage():
    data = dataset()
    projected, diagnostics = radial_projection(data)
    assert diagnostics['supported']
    np.testing.assert_allclose(projected['target'], -1)
    assert np.isclose(projected['weights'].sum(), 1)
    # A rotation is explicitly not collinear; local radial simplification is rejected.
    data['y'] = data['states'][:, [2,1]]*np.array([-1,1])
    assert radial_projection(data)[0] is None
    data = dataset()
    data['states'][:, 2] = 0
    data['y'] = -data['states'][:,1:3]
    assert radial_projection(data)[0] is None


def test_property_ratio_only_uses_complete_varying_properties():
    data = dataset()
    data['X'] = np.column_stack((data['X'], np.arange(1,13), np.arange(2,14)))
    data['feature_names'] += ['mass','charge']
    table, names = feature_table(data)
    np.testing.assert_allclose(table[:, names.index('property_ratio')], np.arange(2,14)/np.arange(1,13))
    data['X'][0,-2] = 0
    assert 'property_ratio' not in feature_table(data)[1]


def test_resolved_small_transverse_force_does_not_select_radial_search():
    # Generic weak circulatory force, unrelated to any development-world law.
    data = dataset()
    position = data['states'][:, 1:3].copy()
    data['y'] = -position + .015*position[:, ::-1]*np.array([-1, 1])
    data['derivative_resolution_mse'] = np.array([1e-10, 1e-10])
    projected, diagnostic = radial_projection(data)
    assert projected is None
    assert diagnostic['relative_transverse_residual'] < .04
    assert diagnostic['relative_transverse_residual'] > diagnostic['effective_transverse_tolerance']
    # Rotating coordinates cannot make the contradiction disappear.
    for angle in (.31, 1.23, 2.71):
        rotation = np.array([[np.cos(angle), -np.sin(angle)],
                             [np.sin(angle), np.cos(angle)]])
        rotated = dict(data, states=data['states'].copy(), y=data['y']@rotation.T)
        rotated['states'][:, 1:3] = position@rotation.T
        other, rotated_diagnostic = radial_projection(rotated)
        assert other is None
        assert np.isclose(rotated_diagnostic['relative_transverse_residual'],
                          diagnostic['relative_transverse_residual'])


def test_projection_allows_unresolved_transverse_discretization_error():
    data = dataset()
    position = data['states'][:, 1:3]
    data['y'] = -position + .001*position[:, ::-1]*np.array([-1, 1])
    signal = np.sum(data['weights'][:, None]*data['y']**2)
    data['derivative_resolution_mse'] = np.array([signal*1e-6/2]*2)
    assert radial_projection(data)[0] is not None
    # Large uncertainty does not remove the conservative absolute relative cap.
    data['y'] = -position + .1*position[:, ::-1]*np.array([-1, 1])
    data['derivative_resolution_mse'] *= 1e6
    assert radial_projection(data)[0] is None
