"""Verify the shipped files, split boundaries, and public certificate coverage."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from serbench import load_dataset, load_labels
from serbench.scoring import validate_labels

def main():
    manifest = json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'))
    for name, meta in manifest['files'].items():
        actual = hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()
        if actual != meta['sha256']:
            raise ValueError('Checksum mismatch: '+name)
    cal, test = load_dataset('cal500', ROOT/'data'), load_dataset('test500', ROOT/'data')
    assert len(cal) == len(test) == 500
    assert not ({r['repo'] for r in cal} & {r['repo'] for r in test})
    for split in (cal, test):
        assert len({r['state_id'] for r in split}) == 500
        for row in split:
            assert not ({'required_evidence_groups','graded_labels','alternative_minimal_sets'} & row.keys())
            candidates=row['candidate_evidence']
            assert len({c['evidence_id'] for c in candidates}) == len(candidates)
            assert all(not ({'role_hints','provenance'} & c.keys()) for c in candidates)
    labels = validate_labels(load_labels('cal500',ROOT/'data'), expected_state_ids={r['state_id'] for r in cal}, candidate_ids_by_state={r['state_id']:{e['evidence_id'] for e in r['candidate_evidence']} for r in cal})
    for label in labels:
        gold={e for g in label['required_evidence_groups'] for e in g['acceptable_evidence_ids']}
        gold.update(e for branch in label.get('alternative_minimal_sets',[]) for e in branch)
        assert not (gold & set(label.get('observed_evidence_ids',[])))
    assert not list((ROOT/'data/test500').glob('*label*'))
    print(json.dumps({'release':manifest['release'],'cal500':len(cal),'test500':len(test),'hashes':'verified','public_interface':'verified'}))

if __name__ == '__main__':
    main()
