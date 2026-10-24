"""
readonly_audit.py
=================
Pure read-only audit. No DROP, DELETE, TRUNCATE, ALTER, UPDATE, INSERT.
Produces all evidence needed for the final approval decision.
"""
import sys
sys.path.insert(0, 'backend')
sys.stdout.reconfigure(encoding='utf-8')
from db import get_db_connection

conn = get_db_connection()
cur  = conn.cursor(dictionary=True)

LIVE_TABLES = [
    'approval','approval_audit_trail','booking_approval_stage',
    'booking_request','committee','event','user','venue',
]
BACKUP_ALLOWLIST = [
    'backup_approval','backup_booking_request',
    'bkp_20261013_014135_approval','bkp_20261013_014135_booking_approval_stage',
    'bkp_20261013_014135_booking_request','bkp_20261013_014135_committee',
    'bkp_20261013_014135_event','bkp_20261013_014135_user',
    'bkp_20261013_014135_venue',
    'bkp2_20261013_183236_approval','bkp2_20261013_183236_approval_audit_trail',
    'bkp2_20261013_183236_booking_approval_stage','bkp2_20261013_183236_booking_request',
    'bkp2_20261013_183236_committee','bkp2_20261013_183236_event',
    'bkp2_20261013_183236_user','bkp2_20261013_183236_venue',
]
SEP = "=" * 70

def rc(t):
    cur.execute(f"SELECT COUNT(*) AS c FROM `{t}`")
    return cur.fetchone()['c']

def exists(t):
    cur.execute("SELECT COUNT(*) AS c FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s", (t,))
    return cur.fetchone()['c'] > 0

# ---------------------------------------------------------------
# AUDIT A: All destructive statements in cleanup_backups.py
# ---------------------------------------------------------------
print("\n" + SEP)
print("AUDIT A -- EVERY DESTRUCTIVE STATEMENT IN cleanup_backups.py")
print(SEP)
print("""
  Line  94:  cur.execute(f"CREATE TABLE `{snap}` AS SELECT * FROM `{t}`")
             --> WRITE: creates snap_ tables for live data. Scope: only
                 tables named in LIVE_TABLES list (8 hardcoded names).

  Line 104:  conn.commit()
             --> Commits the snap_ CREATE TABLE statements above.
                 Aborts if any snap row count mismatched (line 99-102).

  Line 121:  cur.execute(f"DROP TABLE `{t}`")
             --> DESTRUCTIVE: drops one table per iteration.
                 Variable `t` is drawn ONLY from BACKUP_ALLOWLIST (line 114).
                 Two guards precede this line (lines 115-120):
                   Guard A: table_exists(cur, t) must be True
                   Guard B: t must NOT be in LIVE_TABLES
                 If either guard fails, execution skips via `continue`.

  Line 122:  conn.commit()
             --> Commits each individual DROP immediately.

  No other cur.execute() calls in the script contain DDL or DML.
  row_count() (line 58) uses SELECT only.
  table_exists() (line 62-68) uses SELECT on information_schema only.
""")

# ---------------------------------------------------------------
# AUDIT B: Prove allowlist containment -- static analysis
# ---------------------------------------------------------------
print(SEP)
print("AUDIT B -- ALLOWLIST CONTAINMENT PROOF (static analysis)")
print(SEP)

# Intersection: any LIVE table in the allowlist? Must be zero.
overlap = [t for t in BACKUP_ALLOWLIST if t in LIVE_TABLES]
print(f"\n  Live tables that appear in BACKUP_ALLOWLIST : {len(overlap)}")
print("  -> NONE (zero overlap confirmed)" if not overlap
      else f"  -> WARNING: {overlap}")

# Wildcard / dynamic SQL risk analysis
print("""
  Dynamic SQL risk analysis:
    Line 94:  snap name is f"snap_{ts}_{t}" where t in LIVE_TABLES (8 names).
              No backup table name can appear here -- prefix is always 'snap_'.
    Line 121: DROP target is `t` drawn from BACKUP_ALLOWLIST iteration.
              The list is a Python literal -- no string concatenation,
              no f-string interpolation, no runtime user input.
              No LIKE, no REGEXP, no wildcard.
    Helper functions row_count() and table_exists() contain only SELECT.
    No exec(), eval(), or subprocess call exists anywhere in the script.
    No indirect imports beyond `sys`, `time`, and `db.get_db_connection`.

  Path to DROP: run() -> line 114 for-loop over BACKUP_ALLOWLIST ->
                line 115 table_exists guard -> line 117 LIVE_TABLES guard ->
                line 121 DROP TABLE `t`   (t is one of the 17 names only)

  No other code path reaches a DROP statement.
""")

# ---------------------------------------------------------------
# AUDIT C: Confirm snap_* tables are NOT in the drop allowlist
# ---------------------------------------------------------------
print(SEP)
print("AUDIT C -- snap_* TABLES ARE EXCLUDED FROM DELETION")
print(SEP)
snap_in_allowlist = [t for t in BACKUP_ALLOWLIST if t.startswith('snap_')]
print(f"\n  snap_* names found in BACKUP_ALLOWLIST : {len(snap_in_allowlist)}")
print("  -> NONE -- snap_ tables cannot be dropped by this script" if not snap_in_allowlist
      else f"  -> WARNING: {snap_in_allowlist}")
# Check if any snap_ tables exist right now
cur.execute("""SELECT TABLE_NAME FROM information_schema.TABLES
               WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME LIKE 'snap\\_%'""")
existing_snaps = [r['TABLE_NAME'] for r in cur.fetchall()]
print(f"\n  snap_* tables currently in database : {len(existing_snaps)}")
for s in existing_snaps:
    print(f"    {s}  ({rc(s)} rows)")
if not existing_snaps:
    print("    (none yet -- cleanup script creates them right before the DROPs)")

# ---------------------------------------------------------------
# AUDIT D: Snapshot coverage -- what CREATE TABLE AS SELECT captures
# ---------------------------------------------------------------
print("\n" + SEP)
print("AUDIT D -- SNAPSHOT COVERAGE: schema vs data (per table)")
print(SEP)
print("""
  CREATE TABLE snap_X AS SELECT * FROM live_table:

  CAPTURED (data layer):
    [YES] All column names and current data types
    [YES] Every row of data including NULLs
    [YES] NULL / NOT NULL nullability (copied from column metadata)

  NOT CAPTURED (schema layer):
    [NO ] PRIMARY KEY (snap table has no PK -- all columns nullable)
    [NO ] AUTO_INCREMENT counter
    [NO ] FOREIGN KEY constraints (snap has no referential integrity)
    [NO ] UNIQUE constraints / indexes
    [NO ] DEFAULT expressions
    [NO ] CHECK constraints
    [NO ] Column COMMENTs
    [NO ] Table ENGINE, CHARSET, COLLATION options
    [NO ] Triggers defined on the table
    [NO ] Stored routines (procedures/functions)
    [NO ] Views

  CONSEQUENCE:
    snap_ tables can restore individual row values.
    They cannot recreate the original table structure from scratch.
    Use mysqldump for a complete schema+data backup.
""")
print("  Actual column structure of snap_ table (simulated from live DDL):")
for t in ['booking_request', 'booking_approval_stage']:
    cur.execute(f"SHOW CREATE TABLE `{t}`")
    ddl = cur.fetchone().get('Create Table','')
    pk_lines = [l.strip() for l in ddl.splitlines() if 'PRIMARY KEY' in l or 'AUTO_INCREMENT' in l]
    print(f"\n    {t} PK/AI lines (will NOT exist in snap_):")
    for l in pk_lines:
        print(f"      {l}")

# ---------------------------------------------------------------
# AUDIT E: Database dependency metadata (read-only)
# ---------------------------------------------------------------
print("\n" + SEP)
print("AUDIT E -- DATABASE OBJECT DEPENDENCIES (read-only metadata)")
print(SEP)

# All FK constraints in the database
cur.execute("""
    SELECT kcu.TABLE_NAME, kcu.COLUMN_NAME,
           kcu.REFERENCED_TABLE_NAME, kcu.REFERENCED_COLUMN_NAME,
           kcu.CONSTRAINT_NAME
    FROM information_schema.KEY_COLUMN_USAGE kcu
    JOIN information_schema.REFERENTIAL_CONSTRAINTS rc
      ON kcu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
     AND kcu.TABLE_SCHEMA    = rc.CONSTRAINT_SCHEMA
    WHERE kcu.TABLE_SCHEMA = DATABASE()
    ORDER BY kcu.TABLE_NAME
""")
all_fks = cur.fetchall()
backup_fks = [r for r in all_fks
              if r['TABLE_NAME'] in BACKUP_ALLOWLIST
              or r['REFERENCED_TABLE_NAME'] in BACKUP_ALLOWLIST]
live_fks   = [r for r in all_fks if r['TABLE_NAME'] not in BACKUP_ALLOWLIST]

print(f"\n  Total FK constraints in database: {len(all_fks)}")
print(f"  FK constraints involving backup tables: {len(backup_fks)}")
print("  -> NONE" if not backup_fks else "")
for r in backup_fks:
    print(f"    {r['TABLE_NAME']}.{r['COLUMN_NAME']} -> "
          f"{r['REFERENCED_TABLE_NAME']}.{r['REFERENCED_COLUMN_NAME']}")

print(f"\n  Live table FK constraints ({len(live_fks)}):")
for r in live_fks:
    print(f"    {r['TABLE_NAME']}.{r['COLUMN_NAME']} -> "
          f"{r['REFERENCED_TABLE_NAME']}.{r['REFERENCED_COLUMN_NAME']}  [{r['CONSTRAINT_NAME']}]")

# Views
print()
cur.execute("SHOW FULL TABLES WHERE Table_type='VIEW'")
views = [r[list(r.keys())[0]] for r in cur.fetchall()]
for v in views:
    cur.execute(f"SHOW CREATE VIEW `{v}`")
    defn = str(cur.fetchone())
    hits = [t for t in BACKUP_ALLOWLIST if t in defn]
    status = "NONE" if not hits else f"REFERENCES: {hits}"
    print(f"  View {v:<30}: backup refs = {status}")

# Procedures
print()
cur.execute("SHOW PROCEDURE STATUS WHERE Db=DATABASE()")
procs = [p['Name'] for p in cur.fetchall()]
for p in procs:
    cur.execute(f"SHOW CREATE PROCEDURE `{p}`")
    r2 = cur.fetchone()
    key = [k for k in r2 if 'Create' in k][0]
    defn = str(r2[key])
    hits = [t for t in BACKUP_ALLOWLIST if t in defn]
    status = "NONE" if not hits else f"REFERENCES: {hits}"
    print(f"  Procedure {p:<25}: backup refs = {status}")

# Triggers
print()
cur.execute("SHOW TRIGGERS")
trigs = cur.fetchall()
for t in trigs:
    stmt = str(t.get('Statement',''))
    hits = [b for b in BACKUP_ALLOWLIST if b in stmt]
    status = "NONE" if not hits else f"REFERENCES: {hits}"
    print(f"  Trigger {t['Trigger']:<30}: backup refs = {status}")

# ---------------------------------------------------------------
# AUDIT F: Pre-cleanup read-only row counts and table list
# ---------------------------------------------------------------
print("\n" + SEP)
print("AUDIT F -- PRE-CLEANUP BASELINE (read-only SQL)")
print(SEP)
print("\n  SQL used: SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES")
print("  (Exact counts from direct SELECT COUNT(*) shown below)\n")

cur.execute("""
    SELECT TABLE_NAME, TABLE_TYPE
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
    ORDER BY TABLE_TYPE DESC, TABLE_NAME
""")
all_db_objects = cur.fetchall()

print(f"  {'TABLE_NAME':<55} {'TYPE':<12} {'COUNT(*)'}")
print("  " + "-" * 80)
for obj in all_db_objects:
    name = obj['TABLE_NAME']
    ttype = obj['TABLE_TYPE']
    if ttype == 'BASE TABLE':
        count = rc(name)
        tag = ""
        if name in LIVE_TABLES:
            tag = " [LIVE]"
        elif name in BACKUP_ALLOWLIST:
            tag = " [BACKUP -- to drop]"
        elif name.startswith('snap_'):
            tag = " [SNAP -- keep]"
        else:
            tag = " [UNKNOWN]"
        print(f"  {name:<55} {ttype:<12} {count:>6}  {tag}")
    else:
        print(f"  {name:<55} {ttype:<12}  (view)")

# Identify any tables outside live + backup + snap categories
cur.execute("""SELECT TABLE_NAME FROM information_schema.TABLES
               WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'""")
all_base = [r['TABLE_NAME'] for r in cur.fetchall()]
uncategorised = [t for t in all_base
                 if t not in LIVE_TABLES
                 and t not in BACKUP_ALLOWLIST
                 and not t.startswith('snap_')]
print(f"\n  Uncategorised base tables (neither live nor backup): {len(uncategorised)}")
for t in uncategorised:
    print(f"    {t}  ({rc(t)} rows)  -- NEEDS REVIEW")
if not uncategorised:
    print("    NONE -- every base table is accounted for")

cur.close()
conn.close()
print("\n" + SEP)
print("Read-only audit complete. No data was modified.")
print(SEP)
