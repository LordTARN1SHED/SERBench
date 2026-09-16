"""Public Python API for the SERBench benchmark.

The benchmark data is deliberately kept outside the Python package.  Install
this small SDK alongside a released ``data/`` directory (or point
``SERBENCH_DATA_DIR`` at one) and use :func:`load_dataset` and
:func:`load_labels` to read it.
"""

from .data import (
    DataError,
    DataNotFoundError,
    Dataset,
    PrivateLabelsError,
    load_dataset,
    load_labels,
)
from .scoring import (
    ScoringError,
    ValidationError,
    read_predictions,
    score_predictions,
    validate_labels,
    validate_predictions,
)

__all__ = [
    "DataError",
    "DataNotFoundError",
    "Dataset",
    "PrivateLabelsError",
    "ScoringError",
    "ValidationError",
    "load_dataset",
    "load_labels",
    "read_predictions",
    "score_predictions",
    "validate_labels",
    "validate_predictions",
]

__version__ = "0.1.0"

