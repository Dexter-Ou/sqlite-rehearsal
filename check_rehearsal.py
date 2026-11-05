import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from rehearse import rehearse

results = []
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    db = root / 'fixture.db'
    sql = root / 'change.sql'
    with sqlite3.connect(db) as c:
        c.executescript('CREATE TABLE parent(id INTEGER PRIMARY KEY); INSERT INTO parent VALUES(1); CREATE TABLE child(id INTEGER REFERENCES parent(id)); INSERT INTO child VALUES(1);')
    original = hashlib.sha256(db.read_bytes()).hexdigest()
    def check(name, statement, predicate):
        sql.write_text(statement)
        r = rehearse(db, sql)
        assert predicate(r), (name, r)
        assert hashlib.sha256(db.read_bytes()).hexdigest() == original
        results.append({'case': name, 'passed': True})
    check('schema addition', 'ALTER TABLE parent ADD COLUMN label TEXT;', lambda r: r['status']=='completed' and 'label' in r['schema_after']['parent'])
    check('deleted row reported', 'DELETE FROM child;', lambda r: r['row_deltas']['child']==-1)
    check('foreign key loss detected', 'DELETE FROM parent;', lambda r: r['status']=='check_failed' and len(r['foreign_key_violations'])==1)
    check('SQL error explicit', 'ALTER TABLE missing ADD COLUMN x;', lambda r: r['status']=='error')
    check('partial execution disclosed', 'DELETE FROM child; SELECT * FROM missing;', lambda r: r['status']=='error' and r['partial_execution_possible'] and r['rows_after']['child']==0)
    check('attached file denied', "ATTACH DATABASE '" + str(root/'escape.db') + "' AS external;", lambda r: r['status']=='error')
    assert not (root/'escape.db').exists()
    check('pragma side effect denied', 'PRAGMA journal_mode=WAL;', lambda r: r['status']=='error')
    sql.write_text('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n;')
    r = rehearse(db, sql, .01)
    assert r['status']=='error' and 'interrupted' in r['error']
    results.append({'case':'execution deadline', 'passed':True})
    sql.write_text('SELECT 1;')
    for duration in ('nan', 'inf', '-inf', '0', '31'):
        invalid = subprocess.run([sys.executable, 'rehearse.py', str(db), str(sql), '--seconds=' + duration], capture_output=True, text=True, timeout=3)
        assert invalid.returncode == 2 and json.loads(invalid.stdout)['status'] == 'input_error', duration
        assert hashlib.sha256(db.read_bytes()).hexdigest() == original
        results.append({'case': 'invalid duration rejected: ' + duration, 'passed': True})
    Path(str(db)+'-wal').touch()
    try:
        rehearse(db, sql)
        raise AssertionError('sidecar accepted')
    except ValueError:
        results.append({'case':'live sidecar rejected','passed':True})
    Path(str(db)+'-wal').unlink()
    sql.write_text('ALTER TABLE parent ADD COLUMN label TEXT;')
    cli = subprocess.run([sys.executable,'rehearse.py',str(db),str(sql)],capture_output=True,text=True)
    report=json.loads(cli.stdout)
    assert cli.returncode==0 and report['input_bytes_unchanged']
    results.append({'case':'fresh CLI journey','passed':True})
print(json.dumps({'test_kind':'operator-authored synthetic fixtures','cases':results,'passed':len(results),'independent_users':False},indent=2))
