# Paper reference materials

This public release focuses on using SERBench: loading the benchmark, integrating a method, and scoring predictions. It is not a turnkey reproduction of every experiment in the paper.

## Available here

- [Paper on arXiv](https://arxiv.org/abs/2609.20050): the current manuscript and its revision history.
- [Public data and provenance](../data/manifest.json): Cal500 states, candidates and calibration certificates; Test500 states and candidates. Source archives, transformations and checksums are recorded in the manifest.
- [Reference scorer](../src/serbench/_reference_scorer.py): the frozen scoring functions, wrapped by strict public input validation.
- [Frozen primary results](../reference_results/): the twelve primary Test500 methods' aggregate summary files from the v5.6 supplementary release, retained unchanged in the v5.7 supplementary package and the v5.11 manuscript. Fractions should be multiplied by 100 for percentages.
- [Quick start](QUICKSTART.md) and [evaluation protocol](EVALUATION.md): executable examples for new methods.

The included BM25 starter is for onboarding. It is not the paper's frozen BM25 run, and these materials do not claim to regenerate MSS-Complement or the external-validity experiments end to end. Model-dependent experiments also require their specified model access, configurations and inference budgets.

## Held-out evaluation

Test500 certificates remain organizer-private. The automatic evaluation service reports aggregate metrics only. Public reproduction resources do not include private certificates, per-state Test500 scores, or organizer evaluation state. See the [evaluation guide](EVALUATION.md#held-out-test500-evaluation) for submitting a frozen prediction file.

For an experiment not covered by this public interface, contact **zhf023@ucsd.edu** and name the paper table or experiment. Do not infer full experimental coverage from the starter commands.
