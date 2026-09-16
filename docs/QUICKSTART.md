# Bring your own method

## 1. Install from the repository

```bash
git clone https://github.com/LordTARN1SHED/SERBench.git
cd SERBench
python -m pip install -e .
```

The data files are included in this checkout. No Git LFS or model downloads are required. A standalone wheel contains the SDK, not the dataset: set `SERBENCH_DATA_DIR` to the checkout's `data` folder when using another installation. `--data-dir` overrides that setting. Use Python 3.10 or newer.

## 2. Replace the ranking function

Open `examples/custom_method.py` and replace `rank_item(row, k)`. Its input contains the captured state and candidate excerpts; its output must be distinct candidate evidence IDs in ranking order. The scaffold does not load labels or automatically remove observed candidates. Its default source-path ordering is only a wiring example, not a useful retrieval algorithm.

```bash
python examples/custom_method.py --split example --output custom_predictions.jsonl
python -m serbench validate --split example --predictions custom_predictions.jsonl
python -m serbench score --split example --predictions custom_predictions.jsonl --output custom_scores
```

Use `--overwrite` explicitly to repeat a run into the same outputs. Score output files are `summary.json` and `per_state_scores.jsonl`.

## 3. Develop on Cal500

```python
from serbench import load_dataset, load_labels, score_predictions

data = load_dataset("cal500")
# Supply a prediction for each state. Replace this empty-output example.
predictions = [
    {"state_id": row["state_id"], "method": "my_method", "ranked_evidence_ids": []}
    for row in data
]
labels = load_labels("cal500")  # Scoring/development only; keep out of inference.
per_state, summary = score_predictions(predictions, labels, dataset=data)
print(summary)
```

Always pass `dataset` when scoring real predictions. Candidate membership must be checked against the actual pool, not inferred from gold IDs. `--allow-subset` is only for local debugging; partial results are not comparable to full benchmark results or accepted Test500 submissions.

## 4. Freeze and submit

Run your fixed method on Test500 and follow the [offline evaluation instructions](EVALUATION.md#held-out-test500-evaluation). Report your model, settings, resource budget, and release version. Keep credentials in your own environment, never in prediction files or public issues.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No module named serbench` | Run `python -m pip install -e .` from the repository using the same Python interpreter. |
| Dataset not found | Confirm the full repository was downloaded; set `--data-dir /path/to/SERBench/data`. |
| Test500 labels are private | Expected: validate locally and submit predictions to the authors. |
| Missing predictions | Emit one record for every split state, including empty outputs for failures. |
| Unknown evidence ID | Use IDs from the corresponding state's candidates, not another state or a filename. |
| Output exists | Choose a new path or explicitly pass `--overwrite`. |
