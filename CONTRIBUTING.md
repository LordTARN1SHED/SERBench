# Contributing

Bug reports, interface improvements, and documentation fixes are welcome. Include the dataset version, Python version, command, and a minimal reproduction. Use state/evidence IDs where possible instead of pasting large source excerpts.

Run `python -m unittest discover -s tests -v` before proposing changes. Scoring changes must retain reference-scorer parity or explicitly document a versioned protocol change. Do not change frozen labels or silently remove observed candidates.

Do not submit Test500 certificates, secrets, or private user data. Propose dataset corrections as issues with evidence; the maintainers will review them and record any accepted correction as a versioned change, not overwrite a published release without notice.
