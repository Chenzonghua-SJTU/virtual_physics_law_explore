"""Public world identifiers only; physical definitions live in shore_sim.

Neutral labels let the console select a world without giving discovery agents
any hint about its force law. Existing archives belong to world_1.
"""

DEFAULT_WORLD_ID = 'world_1'
WORLD_IDS = tuple(f'world_{index}' for index in range(1, 8))
LEGACY_PHYSICS_VERSION = 'v1'
CURRENT_PHYSICS_VERSION = 'v4'
PHYSICS_VERSIONS = (LEGACY_PHYSICS_VERSION, 'v2', 'v3', CURRENT_PHYSICS_VERSION)


def validate_world_id(value):
    if not isinstance(value, str) or value not in WORLD_IDS:
        raise ValueError('invalid_world_id')
    return value


def validate_physics_version(value):
    if not isinstance(value, str) or value not in PHYSICS_VERSIONS:
        raise ValueError('invalid_physics_version')
    return value


def validate_world_physics(world_id, physics_version):
    world_id = validate_world_id(world_id)
    physics_version = validate_physics_version(physics_version)
    if world_id in ('world_6', 'world_7') and physics_version != 'v4':
        raise ValueError('world_physics_version_mismatch')
    return world_id, physics_version


def world_name(world_id):
    return f'世界 {WORLD_IDS.index(validate_world_id(world_id)) + 1:02d}'


def public_worlds():
    return [{'id': world_id, 'name': world_name(world_id)} for world_id in WORLD_IDS]
