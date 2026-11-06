"""Compact status of all server-local baseline batches."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for path in sorted((root / 'experiments').glob('v15-local-*/summary.json')):
    data = json.loads(path.read_text())
    rows = []
    for row in data['worlds']:
        score = (row.get('evaluation_score') or {}).get('total')
        value = f"{row['world_id'][-1]}:{row['status']}"
        value += f"/{score:.2f}" if score is not None else f"/{row.get('calls') or 0}calls"
        if row.get('reason') and row['status'] != 'submitted':
            value += '/' + row['reason']
        rows.append(value)
    print(path.parent.name, data['status'], ' '.join(rows), flush=True)
