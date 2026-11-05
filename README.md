# SQLite Rehearsal — experimental local prototype

Rehearse a trusted SQL migration against an in-memory copy of a **closed,
checkpointed, disposable SQLite fixture**. The input file is opened read-only.
The JSON report includes schema, table row counts, foreign-key violations,
integrity checks, SQLite version and an explicit partial-execution warning if SQL
fails. There is no apply command. Python 3 standard library only.

```
python3 rehearse.py fixture.db migration.sql > report.json
```

Exit 0 means execution and SQLite checks completed, 1 means execution/check
failure, and 2 means invalid input. Row changes are observations, not automatic
failures. Read the report; a destructive migration can execute successfully.
Use only test data and SQL you trust. This is not a hostile-code sandbox. Do not
point it at live databases, production data, secrets, or arbitrary downloaded SQL.
It refuses visible WAL/journal sidecars and limits fixtures to 32 MiB. The SQL
execution deadline defaults to five seconds; setup/checks are outside this timer.
It uses the runtime SQLite version, not necessarily your deployed version.
Row counts do not detect changed values. Schema text may expose database design.
Application assertions, extension modules, custom functions/collations and
framework-specific migration code are outside this prototype.

Synthetic developer check: `python3 check_rehearsal.py`.
Automated synthetic checks were run on Linux with Python 3.12. Other platforms are untested.

## First run with disposable sample data

Python 3.10 or later is required. From the extracted folder, run:

```sh
python3 example_fixture.py
python3 rehearse.py example.db example.sql > report.json
```

The sample generator refuses to overwrite an existing `example.db`. The supplied
migration adds an `archived` column and deletes one of three sample rows.
Open `report.json`: `status` should be `completed`, `input_bytes_unchanged` true,
`rows_before.items` 3, `rows_after.items` 2 and `row_deltas.items` -1.
`schema_after.items` includes `archived`. This successful execution still deletes
data: decide whether each observed change matches your intended migration.
An empty foreign-key list and `integrity: ["ok"]` only describe SQLite checks.
On `error`, inspect `error` and `partial_execution_possible`; later statements
may not have run and earlier statements may have changed the in-memory copy.
No migrated database file is saved. Keep reports private if schema/row metadata
is sensitive. Delete sample files and reports when finished; original fixtures
are not recovery backups.

## License and feedback

Free MIT-licensed preview from Gong LLC. See LICENSE. Support is best effort,
with no service commitment. To report setup trouble, confusing output or a
missing workflow detail, open an Issue in this repository. Use a small synthetic
example; do not upload real databases, private schemas, secrets or customer data.
