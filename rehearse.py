"""Rehearse trusted SQL against an in-memory copy of an offline SQLite fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import time


def schema(conn):
    return {name: sql for name, sql in conn.execute(
        "SELECT name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY name")}


def counts(conn):
    result = {}
    for (name,) in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        quoted = '"' + name.replace('"', '""') + '"'
        result[name] = conn.execute('SELECT count(*) FROM ' + quoted).fetchone()[0]
    return result


def rehearse(database, migration, seconds=5):
    path = Path(database).resolve(strict=True)
    if seconds <= 0 or seconds > 30:
        raise ValueError('seconds must be greater than 0 and at most 30')
    # Only closed, offline fixtures: immutable reads do not handle live WAL state.
    if Path(str(path) + '-wal').exists() or Path(str(path) + '-journal').exists():
        raise ValueError('use a closed, checkpointed fixture; WAL/journal sidecar found')
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('fixture exceeds 32 MiB prototype limit')
    sql = Path(migration).read_text(encoding='utf-8')
    if len(sql.encode()) > 1024 * 1024:
        raise ValueError('migration exceeds 1 MiB prototype limit')
    before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    conn = sqlite3.connect(':memory:')
    try:
        with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as source:
            source.backup(conn)
        before_schema, before_counts = schema(conn), counts(conn)
        baseline_fk = list(conn.execute('PRAGMA foreign_key_check'))
        baseline_integrity = [r[0] for r in conn.execute('PRAGMA integrity_check')]
        # The authorizer constrains SQL file writes; it is not an OS sandbox.
        def authorize(action, arg1, arg2, db, trigger):
            if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_PRAGMA and arg1.lower() not in ('foreign_keys', 'defer_foreign_keys'):
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION and (arg2 or '').lower() == 'load_extension':
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        conn.set_authorizer(authorize)
        deadline = time.monotonic() + seconds
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        error = None
        try:
            conn.executescript(sql)
        except sqlite3.Error as exc:
            error = str(exc)
        finally:
            conn.set_progress_handler(None, 0)
            conn.set_authorizer(None)
        # On error, report only partial execution; never present it as success.
        after_schema, after_counts = schema(conn), counts(conn)
        fk = list(conn.execute('PRAGMA foreign_key_check'))
        integrity = [r[0] for r in conn.execute('PRAGMA integrity_check')]
        unchanged = hashlib.sha256(path.read_bytes()).hexdigest() == before_hash
        return {
            'sqlite_version': sqlite3.sqlite_version,
            'status': 'error' if error else ('check_failed' if fk or integrity != ['ok'] else 'completed'),
            'error': error, 'partial_execution_possible': bool(error),
            'input_bytes_unchanged': unchanged,
            'baseline_foreign_key_violations': baseline_fk,
            'baseline_integrity': baseline_integrity,
            'foreign_key_violations': fk, 'integrity': integrity,
            'rows_before': before_counts, 'rows_after': after_counts,
            'row_deltas': {k: after_counts.get(k, 0) - before_counts.get(k, 0)
                           for k in sorted(set(before_counts) | set(after_counts))},
            'schema_before': before_schema, 'schema_after': after_schema,
            'limits': 'Offline trusted fixtures/SQL only; no application correctness guarantee. Row counts do not detect value changes. No source writes or migration apply mode.'
        }
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database')
    parser.add_argument('migration')
    parser.add_argument('--seconds', type=float, default=5)
    args = parser.parse_args()
    try:
        report = rehearse(args.database, args.migration, args.seconds)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({'status': 'input_error', 'error': str(exc)}))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'completed' and report['input_bytes_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
