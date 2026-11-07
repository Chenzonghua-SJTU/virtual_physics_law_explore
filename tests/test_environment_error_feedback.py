from shore_agent.runtime import ToolRuntime


def test_environment_failure_keeps_code_and_message_for_next_agent_turn(tmp_path):
    class Environment:
        ruleset = 'e5'
        def request(self, name, **kwargs):
            if name == 'budget':
                return {'ok': True, 'budget': {'wall_seconds_remaining': 100,
                                              'energy_remaining': 0, 'session_ended': False}}
            return {'ok': False, 'error': {'code': 'energy_budget',
                                           'message': 'Not enough energy for this batch'}}
    runtime = ToolRuntime(Environment(), tmp_path)
    runtime.task = {}
    result = runtime.execute('insert_probe', {'probes': [{'r0': [0, 0], 'v0': [0, 0], 'properties': {}}],
                                              't0': 0, 'dt': .1, 'n_samples': 10})
    assert result['error'] == {'code': 'energy_budget', 'message': 'Not enough energy for this batch'}
