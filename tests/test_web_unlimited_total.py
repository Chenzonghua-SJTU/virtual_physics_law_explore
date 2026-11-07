import json

from test_web_jobs import manager, launch


def test_explicit_null_total_budget_survives_form_config_archive_and_projection(manager, launch):
    run_id = manager.start({'api_key': 'synthetic-test', 'max_total_tokens': None,
                            'max_tokens_per_call': 4096})
    config = json.loads((manager.runs_dir/run_id/'config.json').read_text())
    assert config['model']['max_total_tokens'] is None
    assert config['model']['max_tokens_per_call'] == 4096
    assert manager.snapshot(run_id)['limits']['max_total_tokens'] is None
