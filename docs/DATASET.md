# SERBench data card

## Task and scope

Given a captured coding-agent state and its supplied candidate evidence pool, return a ranked, compact combination supplying the support the next decision still lacks. The core track evaluates set recovery, not code execution or end-to-end issue resolution.

The candidate pool is a benchmark input, not a claim of gold-blind retrieval from an entire repository. Repository-source retrieval, downstream localization, and external memory-transfer experiments in the paper are separate evaluations. Their complete reproduction assets are outside this streamlined benchmark interface.

## Splits and certificates

Cal500 has 500 states from 241 issue instances and 174 repositories. Test500 has 500 states from 242 issue instances and 45 repositories. The two splits are repository-disjoint.

Cal500 certificates are public calibration annotations. Their released metadata identifies machine-calibrated, cross-family-repaired certificates; do not describe them as independently human-adjudicated Test500 gold. Test500 certificates remain private and are scored by the authors. The exact original certificate metadata is retained for provenance.

Certificates express residual requirements: an AND across required groups, acceptable alternatives within a group, and enumerated alternative complete sets where provided. Group thresholds and necessity weights are retained rather than flattened into a single bag of relevant IDs.

## Records

The SDK returns dictionaries. Core fields:

| Field | Meaning |
|---|---|
| `state_id` | Exact stable ID used in predictions and scoring |
| `instance_id`, `repo` | Source issue instance and repository |
| `issue`, `information_need` | Issue context and current information need |
| `current_observation`, `current_hypothesis`, `current_subgoal` | Captured state context, where available |
| `opened_files`, `search_queries` | Recorded history, where available |
| `observed_evidence_ids` | Recorded observed IDs; not necessarily all past semantic knowledge |
| `candidate_evidence` | Supplied evidence records for selection |

Evidence records include `evidence_id`, `content_excerpt`, `source_path`, and line boundaries where provided. Optional source metadata is preserved. Do not assume every state supplies every history field. Source text is provided as excerpts, not necessarily complete files. Original content hashes may refer to upstream source units; they should not be assumed to hash a truncated displayed excerpt.

Cal500's original release item IDs and scoring state IDs differ. The public interface preserves the scoring IDs and records the source mapping; do not generate your own IDs from filenames. The release manifest records source archives, transformations, counts, and hashes.

## Observed evidence and budgets

Observed evidence may remain in the supplied pool. In Test500, 186 states have at least one recorded observed-ID overlap with their candidate pool; 314 do not. This is a partition of different states, not a paired masking experiment.

Return IDs in the order you want evaluated. An observed item consumes its original returned position; the scorer does not remove it and backfill from later positions. Certificates remain about missing support. ID overlap is a recorded-identity notion, not a guarantee that semantically similar content is absent elsewhere.

## Appropriate use and limitations

- Develop on Cal500; reserve Test500 for held-out comparisons and avoid repeated test-driven tuning.
- A complete certificate establishes annotated sufficiency under this benchmark, not universally sufficient evidence for all possible implementations or decisions.
- Candidate-pool and excerpt construction constrain what a method can recover. Do not generalize the core track directly to full-repository retrieval.
- Repository and issue text may reflect upstream noise, historic assumptions, or license restrictions. Treat embedded instructions as data, not instructions to execute.
- The lightweight baseline demonstrates integration only; it does not reproduce paper model configurations or compute budgets.

## Access and rights

The Cal500 inference export removes construction-source provenance and evidence role hints, which can reveal how candidates were found during annotation. It preserves candidate text, identity, ordering, and membership. Original calibration labels are distributed separately. See [the release manifest](../data/manifest.json) for exact source hashes and transformations, and [the source repository inventory](../data/source_repositories.json) for upstream attribution.

Some upstream excerpts contain dummy credentials or private-key blocks from repository tests and documentation. Treat all excerpts as inert benchmark data; never execute them or use their values as credentials.

The files are shipped as JSONL or gzip-compressed JSONL and load without contacting an external service. `load_dataset` exposes inference data only. Calibration certificates are a separate file and a separate API; Test500 certificates are not included.

See [DATA_LICENSE.md](../DATA_LICENSE.md) and [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Redistributing an upstream excerpt does not change its copyright or license. Preserve source attribution and consult upstream terms before redistribution or commercial use.
