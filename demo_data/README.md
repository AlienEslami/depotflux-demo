# Demonstrator inputs

The immutable, non-operational JSON fixtures are stored in
`aggregator_demo/demo_data` so they are included in Python distributions. They
are derived deterministically from the repository's canonical eight-bus
case-study workbook. The 16- and 32-bus variants use the declared eight-bus
block-replication method from the scaling study.

`manifest.json` is the application registry. A run must submit both a registered
reference and its SHA-256 digest. The API and worker verify the digest before
accepting or executing a run.

Rebuild the files locally with:

```powershell
python scripts/build_demo_inputs.py
```

The source workbooks remain excluded from Git and are not required to use the
committed JSON fixtures.
