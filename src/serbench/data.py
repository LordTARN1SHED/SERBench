"""Data loading for the public SERBench release.

The release keeps the potentially large item and label files in ``data/``
instead of inside the wheel.  This module only reads JSON Lines (optionally
gzip-compressed) and caches parsed files for the lifetime of the process.
"""

from __future__ import annotations

import gzip
from copy import deepcopy
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Sequence, overload


SPLITS = ("example", "cal500", "test500")


class DataError(RuntimeError):
    """Base class for data discovery and decoding failures."""


class DataNotFoundError(DataError):
    """Raised when a requested public data file is not available."""


class PrivateLabelsError(DataNotFoundError):
    """Raised when Test500 labels are requested from the public release."""


class Dataset(Sequence[dict[str, Any]]):
    """An immutable-in-size sequence of SERBench item dictionaries.

    ``Dataset`` intentionally contains only item rows.  Labels are never
    joined onto rows implicitly; call :func:`load_labels` separately when an
    organizer or a local evaluation needs them.
    """

    __slots__ = ("_rows", "split", "path")

    def __init__(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        split: str | None = None,
        path: Path | None = None,
    ) -> None:
        self._rows = tuple(rows)
        self.split = split
        self.path = path

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._rows)

    def __len__(self) -> int:
        return len(self._rows)

    @overload
    def __getitem__(self, index: int) -> dict[str, Any]: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[dict[str, Any], ...]: ...

    def __getitem__(
        self, index: int | slice
    ) -> dict[str, Any] | tuple[dict[str, Any], ...]:
        return self._rows[index]

    def __repr__(self) -> str:
        suffix = f", split={self.split!r}" if self.split else ""
        return f"Dataset({len(self)} rows{suffix})"


def _validate_split(split: str) -> str:
    if not isinstance(split, str) or split not in SPLITS:
        choices = ", ".join(SPLITS)
        raise ValueError(f"unknown split {split!r}; choose one of: {choices}")
    return split


def _roots(data_dir: str | os.PathLike[str] | None) -> tuple[Path, ...]:
    """Return data roots in precedence order, without requiring any to exist."""

    if data_dir is not None:
        return (Path(data_dir).expanduser(),)

    configured = os.environ.get("SERBENCH_DATA_DIR")
    if configured:
        # An explicit environment override should not silently fall back to a
        # different checkout when the configured path is mistyped.
        return (Path(configured).expanduser(),)

    module_path = Path(__file__).resolve()
    candidates = [
        # Editable source checkout: SERBench/src/serbench/data.py -> SERBench/data.
        module_path.parents[2] / "data",
        # A wheel or a non-standard editable layout may keep data next to the
        # installed package.
        module_path.parents[1] / "data",
        # Running from a release checkout is also supported.
        Path.cwd() / "data",
        Path.cwd(),
    ]
    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(candidate)
    return tuple(unique)


def _file_candidates(root: Path, split: str, stem: str) -> tuple[Path, ...]:
    names = (f"{stem}.jsonl.gz", f"{stem}.jsonl")
    locations = [root / split]
    # When SERBENCH_DATA_DIR points directly at data/example, avoid requiring a
    # redundant nested ``example/example`` directory.
    if root.name == split:
        locations = [root]
    result: list[Path] = []
    seen: set[Path] = set()
    for location in locations:
        for name in names:
            candidate = location / name
            resolved = candidate.resolve(strict=False)
            if resolved not in seen:
                seen.add(resolved)
                result.append(candidate)
    return tuple(result)


def _find_file(
    split: str,
    stem: str,
    data_dir: str | os.PathLike[str] | None,
) -> Path:
    roots = _roots(data_dir)
    candidates: list[Path] = []
    for root in roots:
        for candidate in _file_candidates(root, split, stem):
            candidates.append(candidate)
            if candidate.is_file():
                return candidate
    searched = ", ".join(str(path) for path in candidates)
    raise DataNotFoundError(
        f"SERBench {split!r} {stem} file was not found. Looked for: {searched}. "
        "Install or unpack the public data release, or set "
        "SERBENCH_DATA_DIR to its data directory."
    )


def _open_text(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


@lru_cache(maxsize=16)
def _load_cached(path_string: str, mtime_ns: int, size: int) -> tuple[dict[str, Any], ...]:
    """Decode a file once per path/version.

    ``mtime_ns`` and ``size`` are cache keys so a regenerated release file is
    picked up without requiring callers to restart their process.  The cache
    is intentionally small because each item file can contain large excerpts.
    """

    del mtime_ns, size  # only used to make the cache key versioned
    path = Path(path_string)
    rows: list[dict[str, Any]] = []
    try:
        with _open_text(path) as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DataError(
                        f"invalid JSON in {path} at line {line_number}: {exc.msg}"
                    ) from exc
                if not isinstance(value, dict):
                    raise DataError(
                        f"{path} line {line_number} must contain a JSON object"
                    )
                rows.append(value)
    except OSError as exc:
        raise DataError(f"could not read SERBench data file {path}: {exc}") from exc
    return tuple(rows)


def read_jsonl(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Read a JSONL/JSONL.GZ file of object rows with clear error messages."""

    resolved = Path(path).expanduser()
    try:
        stat = resolved.stat()
    except OSError as exc:
        raise DataError(f"could not stat JSONL file {resolved}: {exc}") from exc
    return deepcopy(list(_load_cached(str(resolved.resolve()), stat.st_mtime_ns, stat.st_size)))


def _load_split_file(
    split: str,
    stem: str,
    data_dir: str | os.PathLike[str] | None,
) -> tuple[list[dict[str, Any]], Path]:
    path = _find_file(split, stem, data_dir)
    try:
        stat = path.stat()
    except OSError as exc:
        raise DataError(f"could not stat SERBench data file {path}: {exc}") from exc
    return (
        deepcopy(list(_load_cached(str(path.resolve()), stat.st_mtime_ns, stat.st_size))),
        path,
    )


def load_dataset(
    split: str,
    data_dir: str | os.PathLike[str] | None = None,
) -> Dataset:
    """Load item rows for ``example``, ``cal500``, or ``test500``.

    ``data_dir`` takes precedence over ``SERBENCH_DATA_DIR``.  With neither,
    the loader checks a source checkout's ``data/`` directory and then the
    current working directory.  Labels are never loaded by this function.
    """

    split = _validate_split(split)
    rows, path = _load_split_file(split, "items", data_dir)
    return Dataset(rows, split=split, path=path)


def load_labels(
    split: str,
    data_dir: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    """Load labels separately from item rows.

    The public Test500 release intentionally contains no labels.  A clear
    :class:`PrivateLabelsError` is raised when they are requested and no local
    organizer-provided label file is available.
    """

    split = _validate_split(split)
    try:
        rows, _ = _load_split_file(split, "labels", data_dir)
    except DataNotFoundError as exc:
        if split == "test500":
            raise PrivateLabelsError(
                "Test500 labels are private and are not included in the public "
                "release; scoring this split requires an organizer-supplied "
                "labels file."
            ) from exc
        raise
    return rows


__all__ = [
    "SPLITS",
    "DataError",
    "DataNotFoundError",
    "Dataset",
    "PrivateLabelsError",
    "load_dataset",
    "load_labels",
    "read_jsonl",
]
