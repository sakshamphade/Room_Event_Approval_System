"""
Full DB inspection: tables, row counts, triggers, views,
stored procedures, events, FK dependencies.
"""
import sys, json
sys.path.insert(0, 'backend')
from db import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

# ── 1. All base tables ────────────────────────────────────────
cur.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
all_tables = [r[list(r.keys())[0]] for r in cur.fetchall()]

backup_tables = sorted([t for t in all_tables if t.startswith(('bkp_','bkp2_','backup_'))])
live_tables   = sorted([t for t in all_tables if not t.startswith(('bkp_','bkp2_','backup_'))])

print("=" * 65)
print("1. TABLE INVENTORY")
print("=" * 65)
print(f"\nBACKUP TABLES ({len(backup_tables)}):")
for t in backup_tables:
    cur.execute(f"SELECT COUNT(*) AS c FROM `{t}`")
    print(f"  {t:<52} {cur.fetchone()['c']:>4} rows")

print(f"\nLIVE TABLES ({len(live_tables)}):")
for t in live_tables:
    cur.execute(f"SELECT COUNT(*) AS c FROM `{t}`")
    print(f"  {t:<52} {cur.fetchone()['c']:>4} rows")

# ── 2. Views ─────────────────────────────────────────────────
cur.execute("SHOW FULL TABLES WHERE Table_type = 'VIEW'")
views = [r[list(r.keys())[0]] for r in cur.fetchall()]
print(f"\n{'='*65}\n2. VIEWS ({len(views)})")
for v in views:
    print(f"  {v}")

# ── 3. Triggers ───────────────────────────────────────────────
cur.execute("SHOW TRIGGERS")
triggers = cur.fetchall()
print(f"\n{'='*65}\n3. TRIGGERS ({len(triggers)})")
for t in triggers:
    print(f"  {t['Trigger']:<40} {t['Timing']} {t['Event']} ON {t['Table']}")

# ── 4. Stored procedures & functions ────────────────────────
cur.execute("SHOW PROCEDURE STATUS WHERE Db = DATABASE()")
procs = cur.fetchall()
cur.execute("SHOW FUNCTION STATUS WHERE Db = DATABASE()")
funcs = cur.fetchall()
print(f"\n{'='*65}\n4. STORED PROCEDURES ({len(procs)})  FUNCTIONS ({len(funcs)})")
for p in procs:  print(f"  PROC: {p['Name']}")
for f in funcs:  print(f"  FUNC: {f['Name']}")
if not procs and not funcs:
    print("  (none)")

# ── 5. Scheduled events ───────────────────────────────────────
cur.execute("SHOW EVENTS")
events = cur.fetchall()
print(f"\n{'='*65}\n5. SCHEDULED EVENTS ({len(events)})")
for e in events: print(f"  {e['Name']}")
if not events: print("  (none)")

# ── 6. FK dependencies touching backup tables ────────────────
cur.execute("""
    SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME,
           CONSTRAINT_NAME
    FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE()
      AND REFERENCED_TABLE_NAME IS NOT NULL
""")
fk_rows = cur.fetchall()
backup_fks = [r for r in fk_rows
              if r['TABLE_NAME'].startswith(('bkp_','bkp2_','backup_'))
              or r['REFERENCED_TABLE_NAME'].startswith(('bkp_','bkp2_','backup_'))]

print(f"\n{'='*65}\n6. FOREIGN KEYS INVOLVING BACKUP TABLES ({len(backup_fks)})")
if backup_fks:
    for r in backup_fks:
        print(f"  {r['TABLE_NAME']}.{r['COLUMN_NAME']} -> "
              f"{r['REFERENCED_TABLE_NAME']}.{r['REFERENCED_COLUMN_NAME']}  [{r['CONSTRAINT_NAME']}]")
else:
    print("  NONE — backup tables have no FK relationships")

# ── 7. Live table FKs (confirm live schema intact) ───────────
live_fks = [r for r in fk_rows if r['TABLE_NAME'] in live_tables]
print(f"\n{'='*65}\n7. LIVE TABLE FOREIGN KEYS ({len(live_fks)})")
for r in live_fks:
    print(f"  {r['TABLE_NAME']}.{r['COLUMN_NAME']} -> "
          f"{r['REFERENCED_TABLE_NAME']}.{r['REFERENCED_COLUMN_NAME']}")

# ── 8. Compare backup vs live row counts for key tables ──────
print(f"\n{'='*65}\n8. SNAPSHOT COMPARISON (backup rows vs live rows)")
print(f"{'Table':<35} {'Backup-1 rows':>14} {'Backup-2 rows':>14} {'Live rows':>10}")
print("-" * 75)
key = ['approval','booking_approval_stage','booking_request',
       'committee','event','user','venue']
for t in key:
    b1 = f"bkp_20261013_014135_{t}"
    b2 = f"bkp2_20261013_183236_{t}"
    def rc(tname):
        try:
            cur.execute(f"SELECT COUNT(*) AS c FROM `{tname}`")
            return str(cur.fetchone()['c'])
        except: return "N/A"
    print(f"  {t:<33} {rc(b1):>14} {rc(b2):>14} {rc(t):>10}")

cur.close()
conn.close()
print(f"\n{'='*65}")
print("Inspection complete.")
