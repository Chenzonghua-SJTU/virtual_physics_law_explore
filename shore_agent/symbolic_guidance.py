"""Pure, auditable SR experiment review using current-session public records only.

No tool execution, formula selection, simulation, archive access or truth inputs.
The caller owns the one-shot flag and decides whether to deliver this advice.
"""
from __future__ import annotations

import math


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _control_key(probe, *, include_properties=True):
    initial = probe.get('initial_conditions', {})
    r, v = initial.get('r0'), initial.get('v0')
    if not all(isinstance(a, (list, tuple)) and len(a) == 2 and all(_finite(x) for x in a)
               for a in (r, v)):
        return None
    key = tuple(round(float(x), 12) for x in (*r, *v))
    if include_properties:
        properties = initial.get('properties', {})
        key += tuple((name, round(float(value), 12)) for name, value in sorted(properties.items())
                     if _finite(value))
    return key


def _position_scale(probe):
    points = probe.get('r_obs', [])
    if not points or not all(isinstance(p, (list, tuple)) and len(p) == 2
                             and all(_finite(x) for x in p) for p in points):
        return None
    first = probe.get('initial_conditions', {}).get('r0', points[0])
    if len(first) != 2 or not all(_finite(x) for x in first):
        return None
    return math.sqrt(sum(sum((p[i]-first[i])**2 for i in range(2)) for p in points)/len(points))


def _validation_warnings(records, probes, law_id, task):
    result = []
    sigma = task.get('position_noise_sigma', 0.)
    sigma = float(sigma) if _finite(sigma) and sigma >= 0 else 0.
    noise = math.sqrt(2)*sigma
    reference = task.get('reference_length', 1.)
    reference = abs(float(reference)) if _finite(reference) and reference else 1.
    floor = 1e-9*reference
    for record_id, validation in records.get('validation', {}).items():
        if validation.get('law_id') != law_id:
            continue
        for row in validation.get('errors', {}).get('per_probe', []):
            probe_id, error = row.get('probe_id'), row.get('position_rmse')
            scale = _position_scale(probes.get(probe_id, {}))
            if scale is None or not _finite(error) or error < 0:
                continue
            normalized = error/max(scale, noise, floor)
            # A continuation cue, never a scientific pass/fail criterion.
            if normalized >= .2 and error > max(5*noise, floor):
                result.append({'validation_id': record_id, 'probe_id': probe_id,
                               'position_rmse': error, 'observed_position_rms_change': scale,
                               'relative_to_observed_change': normalized,
                               'interpretation': 'large_relative_residual; diagnostic only, not an official threshold'})
    return result


def build_review(records, budget, task=None, *, train_probe_ids=None, law_id=None,
                 already_reviewed=False, symbolic_enabled=True):
    """Return one advisory payload, or None when disabled/already sent/too late.

    ``records`` is the existing Store.records mapping. Pass explicit training
    IDs when reviewing a search request; otherwise an existing law's training
    IDs are preferred, or acquired probes are summarized without selecting them.
    Never silently promote unselected or reserved validation probes into search.
    """
    remaining = budget.get('wall_seconds_remaining', 0)
    if (not symbolic_enabled or already_reviewed or budget.get('session_ended')
            or not _finite(remaining) or remaining <= 35):
        return None
    task = task or {}
    probes = records.get('probe', {})
    usable = {key: probe for key, probe in probes.items()
              if isinstance(probe, dict) and len(probe.get('times', [])) >= 3
              and len(probe.get('v_obs', [])) == len(probe.get('times', []))}
    if not usable:
        return None
    law = records.get('law', {}).get(law_id, {})
    requested_ids = list(train_probe_ids if train_probe_ids is not None
                         else law.get('train_probe_ids', usable))
    selected = {key: usable[key] for key in requested_ids if key in usable}
    allowed = [key for key in task.get('allowed_properties', ('mass', 'charge'))
               if key in ('mass', 'charge')]
    property_values, available_contrasts = {}, {}
    for name in allowed:
        values = sorted({float(p['initial_conditions']['properties'][name]) for p in selected.values()
                         if _finite(p.get('initial_conditions', {}).get('properties', {}).get(name))})
        property_values[name] = values
        if len(values) == 1:
            matches = [key for key, p in usable.items() if key not in selected
                       and _finite(p.get('initial_conditions', {}).get('properties', {}).get(name))
                       and p['initial_conditions']['properties'][name] != values[0]]
            if matches:
                available_contrasts[name] = matches
    time_pairs = []
    items = list(selected.items())
    for index, (first_id, first) in enumerate(items):
        key = _control_key(first)
        if key is None:
            continue
        for second_id, second in items[index+1:]:
            if _control_key(second) != key:
                continue
            t1 = first.get('initial_conditions', {}).get('t0')
            t2 = second.get('initial_conditions', {}).get('t0')
            if _finite(t1) and _finite(t2) and abs(t2-t1) > 1e-10:
                time_pairs.append({'probe_ids': [first_id, second_id], 'launch_time_difference': abs(t2-t1)})
    positions = [p.get('initial_conditions', {}).get('r0') for p in selected.values()]
    positions = [p for p in positions if isinstance(p, (list, tuple)) and len(p) == 2
                 and all(_finite(x) for x in p)]
    velocities = {tuple(p['initial_conditions']['v0']) for p in selected.values()
                  if _control_key(p) is not None}
    coordinate_coverage = {axis: {'negative': any(p[index] < 0 for p in positions),
                                  'positive': any(p[index] > 0 for p in positions)}
                           for index, axis in enumerate(('x', 'y'))}
    reasons = []
    if len(usable) >= 3 and not records.get('symbolic_search'):
        reasons.append('symbolic_search_not_attempted_with_available_training_data')
    if available_contrasts:
        reasons.append('unselected_acquired_property_contrasts')
    if any(len(values) < 2 for values in property_values.values()):
        reasons.append('open_properties_not_varied_in_training')
    if not time_pairs:
        reasons.append('no_same_complete_initial_state_delayed_launch_control')
    if positions and (not all(v['negative'] and v['positive'] for v in coordinate_coverage.values())
                      or not any(p[0] != 0 and p[1] != 0 for p in positions)):
        reasons.append('limited_sign_or_off_axis_initial_positions')
    if len(velocities) < 2:
        reasons.append('limited_initial_velocity_controls')
    if law.get('fit_status') in ('not_converged', 'failed', 'error'):
        reasons.append('selected_fit_not_converged')
    validation = _validation_warnings(records, usable, law_id, task) if law_id else []
    if validation:
        reasons.append('selected_law_large_relative_validation_residual')
    searches = list(records.get('symbolic_search', {}).values())
    latest_search = searches[-1] if searches else {}
    if latest_search and not (latest_search.get('candidates')
                             or any(latest_search.get('axis_candidates', {}).values())):
        reasons.append('latest_search_has_no_usable_candidates')
    if not reasons:
        return None
    energy = budget.get('energy_remaining')
    capacity = max(0, int(energy)-2) if _finite(energy) else None
    can_search = remaining >= 100 and len(selected) >= 3
    return {'kind': 'symbolic_experiment_review', 'one_time_only': True, 'advisory_only': True,
            'tool_executed': False, 'law_id': law_id, 'reasons': reasons,
            'budget': dict(budget), 'new_training_probe_capacity_preserving_two_energy': capacity,
            'recommended_search_seconds': 47 if can_search else None,
            'acquired_probe_ids_retained': list(usable), 'reviewed_probe_ids': list(selected),
            'unselected_acquired_property_contrasts': available_contrasts,
            'coverage': {'selected_property_values': property_values,
                         'same_complete_initial_state_time_controls': time_pairs[:4],
                         'same_complete_initial_state_time_control_count': len(time_pairs),
                         'initial_coordinate_signs': coordinate_coverage,
                         'distinct_initial_velocities': len(velocities)},
            'validation_evidence': validation[:3], 'validation_evidence_count': len(validation),
            'instructions': [
                '既有观测、候选和草稿不会因一次搜索失败失效；保留它们，勿原样反复调用。',
                '缺口只是可辨识性提醒，不预设力的形式；仅补最有区分力的对照，不为补齐清单耗尽预算。',
                ('可考虑47秒搜索已有训练数据；新增探针前先核对机动能量，保留两枚新验证能量。'
                 if can_search else '余时或数据不足以建议完整47秒搜索；优先已有候选的必要检验与及时保存草稿。'),
                ('若补实验，仅在上述机动额度内选择最缺的属性、速度或延迟t0对照。'
                 if capacity and remaining >= 70 else '当前不建议新增训练探针；可继续使用已有训练数据和候选。'),
                '未选对照编号仅供明确规划，不自动加入训练；加入搜索后不能再当独立验证。',
                '未收敛或明显验证反证应促使更换结构或补关键对照，不能自行宣布正确；残差阈值不是官方通过标准。',
                '这是一次回顾；如无可行改进，如实说明局限后仍可提交，不无限阻止交卷。']}
