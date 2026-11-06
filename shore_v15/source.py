"""Load the unmodified simulator snapshot only in an observation/evaluation process.

The vendor directory contains no agent package and no external project is added
to sys.path. SOURCE.json records hashes of the original public v15 files.
"""
from pathlib import Path
import sys

_VENDOR = str(Path(__file__).resolve().parent / 'vendor')
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

from development_worlds import catalog
from development_worlds.worlds import DevelopmentSimulator, SINGLE_CENTER
from rift_numerics import DT, NUMERICS_VERSION, rollout, state_rollout


def source_inputs(world, properties):
    """Map the existing tool's two scalar controls to public world inputs."""
    if str(world) in SINGLE_CENTER:
        return {'p1': properties.get('charge', 1.)}, {'p2': properties.get('mass', 1.)}
    return {}, {'mass': properties.get('mass', 1.)}


def agent_properties(world, source, probe):
    if str(world) in SINGLE_CENTER:
        return {'mass': probe['p2'], 'charge': source['p1']}
    return {'mass': probe['mass']}
