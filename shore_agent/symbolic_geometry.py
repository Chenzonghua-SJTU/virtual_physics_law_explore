"""Generic coordinate features and a data-tested vector projection hypothesis.

No simulator, world catalogue, force template, or fitted physical constant.
Aliases are expanded back to ordinary state expressions before tool export.
"""
from __future__ import annotations

import ast
import copy
import numpy as np

ALIASES = {
    'radius2': 'x*x+y*y', 'radius': 'sqrt(x*x+y*y)',
    'speed2': 'vx*vx+vy*vy', 'radial_dot': 'x*vx+y*vy',
    'property_ratio': 'charge/mass',
}


def feature_table(dataset):
    names = list(dataset['feature_names'])
    values = [dataset['X'][:, i] for i in range(len(names))]
    state = dataset['states']
    x, y, vx, vy = (state[:, i] for i in (1, 2, 3, 4))
    options = {'radius2': x*x+y*y, 'radius': np.hypot(x, y),
               'speed2': vx*vx+vy*vy, 'radial_dot': x*vx+y*vy}
    if 'mass' in names and 'charge' in names:
        mass, charge = (dataset['X'][:, names.index(k)] for k in ('mass', 'charge'))
        if np.all(np.abs(mass) > 1e-12): options['property_ratio'] = charge/mass
    for key, value in options.items():
        dependencies = {'radius2': ('x','y'), 'radius': ('x','y'),
                        'speed2': ('vx','vy'), 'radial_dot': ('x','y','vx','vy'),
                        'property_ratio': ('mass','charge')}[key]
        # A dropped constant state variable is not silently reintroduced by an alias.
        if (all(k in names for k in dependencies) and np.isfinite(value).all()
                and np.max(np.abs(value)) <= 1e12 and np.ptp(value) > 1e-12):
            names.append(key); values.append(value)
    return (np.column_stack(values) if values else np.empty((len(state), 0))), names


def expand_aliases(source):
    class Expand(ast.NodeTransformer):
        def visit_Name(self, node):
            return copy.deepcopy(ast.parse(ALIASES[node.id], mode='eval').body) if node.id in ALIASES else node
    tree = Expand().visit(ast.parse(source, mode='eval'))
    return ast.unparse(ast.fix_missing_locations(tree))


def radial_projection(dataset, *, tolerance=.04):
    """Propose a scalar multiplier only when acquired vectors support collinearity.

    This is a hypothesis about these observations, not a symmetry assumption.
    General component searches remain available, including direction dependence.
    """
    if not {'x', 'y'} <= set(dataset['feature_names']):
        return None, {'supported': False, 'reason': 'both_coordinate_features_required'}
    position = dataset['states'][:, 1:3]
    acceleration = dataset['y']
    r2 = np.sum(position*position, axis=1)
    if np.any(r2 < 1e-10) or len(position) < 6:
        return None, {'supported': False, 'reason': 'insufficient_nonzero_position_states'}
    weights = dataset['weights']
    signal = float(np.sum(weights[:, None]*acceleration**2))
    if signal < 1e-20:
        return None, {'supported': False, 'reason': 'acceleration_signal_too_small'}
    scalar = np.sum(position*acceleration, axis=1)/r2
    perpendicular = acceleration-scalar[:, None]*position
    error = float(np.sqrt(np.sum(weights[:, None]*perpendicular**2)/signal))
    angular = position/np.sqrt(r2)[:, None]
    eigenvalues = np.linalg.eigvalsh(angular.T@(weights[:, None]*angular))
    supported = error <= tolerance and eigenvalues[0] > .02
    diagnostics = {'supported': bool(supported), 'relative_transverse_residual': error,
                   'direction_coverage_min_eigenvalue': float(eigenvalues[0]),
                   'hypothesis': 'acceleration equals an unknown scalar response times position',
                   'scope': 'Acquired-data hypothesis only; not proof of isotropy or an origin force source.'}
    if not supported: return None, diagnostics
    # Scalar loss weighted by r² equals vector acceleration loss for this hypothesis.
    projected_weights = weights*r2
    projected_weights /= projected_weights.sum()
    return {'target': scalar, 'weights': projected_weights}, diagnostics
