"""Create a disposable sample; never overwrite an existing database."""
from pathlib import Path
import sqlite3

path = Path('example.db')
with path.open('xb'):
    pass
with sqlite3.connect(path) as conn:
    conn.executescript("CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT); INSERT INTO items VALUES(1,'alpha'),(2,'beta'),(3,'gamma');")
print('Created example.db with three synthetic items')
