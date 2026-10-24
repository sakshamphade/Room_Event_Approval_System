import sys
sys.path.insert(0, 'backend')
from db import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

cur.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
rows = cur.fetchall()

backup = []
live = []

for row in rows:
    name = row[0]
    if name.startswith('bkp') or name.startswith('backup'):
        backup.append(name)
    else:
        live.append(name)

print("=" * 60)
print("BACKUP TABLES")
print("=" * 60)
for t in sorted(backup):
    cur.execute(f"SELECT COUNT(*) FROM `{t}`")
    count = cur.fetchone()[0]
    print(f"  {t:<50} {count:>5} rows")

print()
print("=" * 60)
print("LIVE APPLICATION TABLES")
print("=" * 60)
for t in sorted(live):
    cur.execute(f"SELECT COUNT(*) FROM `{t}`")
    count = cur.fetchone()[0]
    print(f"  {t:<50} {count:>5} rows")

print()
print(f"Total backup tables : {len(backup)}")
print(f"Total live tables   : {len(live)}")

cur.close()
conn.close()
