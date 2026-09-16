"""Run the SERBench command-line interface with ``python -m serbench``."""

from .cli import main


if __name__ == "__main__":  # pragma: no cover - exercised by subprocess tests
    raise SystemExit(main())

