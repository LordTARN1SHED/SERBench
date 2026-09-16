"""Generate a full-abstention Test500 file for service integration testing.

This is not a retrieval method or a paper result. It deliberately returns no
evidence and should score zero on all five primary aggregate metrics.
"""
import json
from pathlib import Path
from serbench import load_dataset

destination = Path('examples/service_smoke.jsonl')
with destination.open('x', encoding='utf-8', newline='\n') as handle:
    for state in load_dataset('test500'):
        handle.write(json.dumps({'state_id':state['state_id'], 'method':'service-integration-abstention', 'ranked_evidence_ids':[]})+'\n')
print(destination)
