# Evaluation guide

## Prediction contract

Write UTF-8 JSONL, one object per state per method:

```json
{"state_id":"COPY_THE_EXACT_DATASET_STATE_ID","method":"my_method","ranked_evidence_ids":["COPY_A_CANDIDATE_EVIDENCE_ID"]}
```

Use IDs from that state's candidate pool. Preserve ranking order. Include every state in the selected split for every reported method. Duplicate state/method pairs, duplicate returned IDs, unknown states, and out-of-pool evidence IDs are errors, not silently repaired inputs. An empty list is a valid abstention; omitted states are not a way to exclude failures.

Return at least eight distinct candidates if your method is designed to fill an eight-item budget. Shorter outputs are scored as returned. Never pad with invalid IDs or reorder after seeing labels. All top-k metrics operate on the original first k positions, without masking observed items or backfilling.

## Local calibration

```bash
python -m serbench validate --split cal500 --predictions predictions.jsonl
python -m serbench score --split cal500 --predictions predictions.jsonl --k 5 8 --output scores
```

Scores are macro-averaged over states, not repository averages. Metric values in machine-readable output are fractions; multiply by 100 for percentages. The reference scorer is retained from the v5.6 release, with strict input checks at the interface boundary.

| Paper measure | Output key | Interpretation |
|---|---|---|
| Complete-MSS@k | `mss_complete@k` | All required groups meet their thresholds, or a certified alternative complete set is covered |
| Group@k | `group_recall@k` | Fraction of required groups completed |
| Necessity@k | `necessity_weighted_recall@k` | Completed-group recall weighted by certificate necessity weights |

The primary paper suite is Complete@5, Complete@8, Group@5, Group@8, and Necessity@5. Additional reference metrics may also be emitted; they do not replace this suite. Within a group, distinct acceptable IDs count toward `minimum_required`. One evidence unit may satisfy more than one group when the certificate explicitly permits it.

## Held-out Test500 evaluation

1. Freeze your method after calibration. Run it over all 500 Test500 states using only released inference inputs.
2. Validate locally:

   ```bash
   python -m serbench validate --split test500 --predictions test_predictions.jsonl
   ```

3. Save the UTF-8 `.jsonl` file in a **public repository owned by your submitting GitHub account**. Use an immutable raw URL with the full 40-character commit SHA: `https://raw.githubusercontent.com/YOUR_ACCOUNT/YOUR_REPO/COMMIT_SHA/predictions.jsonl`. Branch URLs, redirects, compressed files, external hosts, and executable submissions are not accepted. Maximum size: 2 MiB; exactly one method, 500 states, and at most eight IDs per state.
4. Calculate the file's SHA-256, or use the website's local validation tool. Open a [Test500 evaluation request](https://github.com/LordTARN1SHED/SERBench/issues/new?template=evaluation.yml) and provide the URL, hash, release `serbench-public-v1-v5.6`, method configuration, and publication consent. Your predictions, method description, and aggregate scores are public. Do not include credentials or confidential material.
5. The private evaluator polls the queue on a 30-minute schedule once configured and enabled. GitHub may delay scheduled jobs; there is no guaranteed turnaround. Results appear as a comment on your issue. The live website status indicates whether the service is enabled; until activation, contact **zhf023@ucsd.edu** for author-assisted scoring.

The private service is active and has passed an end-to-end full-abstention test. It returns the five primary aggregate metrics, not per-state scores, certificate contents, or evidence roles. One accepted evaluation per GitHub account per seven days limits test-driven tuning; it is not a guarantee against multiple-account abuse. Edited requests are not silently rescored. Empty predictions for a state are permitted and counted as failures, rather than omitted.

Accepted evaluation comments automatically refresh [community_results.json](../community_results.json). The website reads this public feed every five minutes while open; scoring and publication can be delayed by GitHub. Paper reference results remain a separate frozen table. Editing a scored issue's body or deleting its result comment removes it from the next successful feed rebuild. Failed refreshes retain the previous feed; check its publication timestamp and the linked issue when in doubt.

Scoring code and metric definitions remain public. Only Test500 certificates and evaluation state are private. Local Test500 scoring requires an explicit organizer-supplied `--labels` path; never add that file to a public release. For confidential predictions, contact the authors instead of opening a public issue.

## Reporting a result

Report the split, all five primary metrics, number of states, method configuration, budget, dataset version, and whether source text beyond the supplied candidates was accessed. Distinguish the supplied-candidate track from full-repository retrieval. Do not compare a three-state example run to the paper's Test500 table.

For uncertainty estimates or significance claims, describe the resampling and paired comparison procedure separately; a single aggregate score does not establish significance. The starter CLI is a scoring interface, not a replacement for the paper's full statistical analysis archive.
