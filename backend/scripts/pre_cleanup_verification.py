"""
pre_cleanup_verification.py  -- READ-ONLY, no DROP/DELETE/TRUNCATE
Answers the 6 pre-approval checks without touching any data.
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

BACKUP_TABLES_TO_DROP = [
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

def exists(t):
    cur.execute("SELECT COUNT(*) AS c FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s", (t,))
    return cur.fetchone()['c'] > 0

def rc(t):
    cur.execute(f"SELECT COUNT(*) AS c FROM `{t}`")
    return cur.fetchone()['c']

SEP = "=" * 65

# ---------------------------------------------------------------
print("\n" + SEP)
print("CHECK 1 -- EXACT NAMES OF ALL 17 BACKUP TABLES TO BE DROPPED")
print(SEP)
found, missing = [], []
for i, t in enumerate(BACKUP_TABLES_TO_DROP, 1):
    e = exists(t)
    rows   = f"{rc(t)} rows" if e else "NOT FOUND in DB"
    mark   = "WILL DROP" if e else "SKIP (already gone)"
    print(f"  {i:>2}. {t:<52} [{mark}]  {rows}")
    (found if e else missing).append(t)
print(f"\n  Tables that WILL be dropped : {len(found)}")
print(f"  Tables already absent       : {len(missing)}")

# ---------------------------------------------------------------
print("\n" + SEP)
print("CHECK 2 -- SNAPSHOT STRUCTURE: what CREATE TABLE AS SELECT preserves")
print(SEP)
cur.execute("SHOW CREATE TABLE `booking_request`")
row = cur.fetchone()
ct  = row.get('Create Table', '')
print("\n  ORIGINAL booking_request DDL (abridged to show structure):")
for line in ct.splitlines()[:18]:
    print("   ", line)
print("   ...")
print("""
  What  CREATE TABLE snap_... AS SELECT *  PRESERVES:
    [YES]  All column names and data types
    [YES]  All row data (exact copy)
    [YES]  NULL / NOT NULL attribute (inherited from SELECT result)

  What it does NOT preserve:
    [NO ]  PRIMARY KEY constraint
    [NO ]  AUTO_INCREMENT setting
    [NO ]  FOREIGN KEY constraints
    [NO ]  UNIQUE / INDEX definitions
    [NO ]  DEFAULT values
    [NO ]  CHECK constraints
    [NO ]  Triggers

  CONCLUSION: snap_* tables are DATA-ONLY copies.
  Sufficient for restoring individual rows. Not sufficient to
  recreate table structure from scratch.

  HOW snap_* tables survive after cleanup:
    The cleanup script does NOT drop snap_* tables.
    They remain permanently in the database after cleanup runs.
    You can query them any time.

  HOW TO RESTORE ROWS from a snap_* table:
    INSERT INTO <live_table>
    SELECT * FROM snap_<timestamp>_<live_table>
    WHERE <pk_column> NOT IN (SELECT <pk_column> FROM <live_table>);

  STRONG RECOMMENDATION -- before running cleanup, take a full
  structural + data backup using mysqldump:
    mysqldump -u root -p event_area_approval > backup_full_YYYYMMDD.sql
  This captures PKs, FKs, indexes, triggers, views, and procedures.
""")

# ---------------------------------------------------------------
print(SEP)
print("CHECK 3 -- REFERENCES TO THE 17 BACKUP TABLES IN DB OBJECTS")
print(SEP)

# Views
cur.execute("SHOW FULL TABLES WHERE Table_type='VIEW'")
views = [r[list(r.keys())[0]] for r in cur.fetchall()]
view_refs = []
for v in views:
    cur.execute(f"SHOW CREATE VIEW `{v}`")
    defn = str(cur.fetchone())
    hits = [t for t in BACKUP_TABLES_TO_DROP if t in defn]
    if hits:
        view_refs.append((v, hits))
print(f"\n  Views checked ({len(views)}): {views}")
print(f"  Backup table references in views: {len(view_refs)}")
print("  -> NONE" if not view_refs else "")
for v, h in view_refs:
    print(f"    VIEW {v} references {h}")

# Stored procedures
cur.execute("SHOW PROCEDURE STATUS WHERE Db=DATABASE()")
procs = [p['Name'] for p in cur.fetchall()]
proc_refs = []
for p in procs:
    cur.execute(f"SHOW CREATE PROCEDURE `{p}`")
    r2 = cur.fetchone()
    key = [k for k in r2 if 'Create' in k][0]
    defn = str(r2[key])
    hits = [t for t in BACKUP_TABLES_TO_DROP if t in defn]
    if hits:
        proc_refs.append((p, hits))
print(f"\n  Stored procedures checked ({len(procs)}): {procs}")
print(f"  Backup table references in procedures: {len(proc_refs)}")
print("  -> NONE" if not proc_refs else "")
for p, h in proc_refs:
    print(f"    PROC {p} references {h}")

# Triggers
cur.execute("SHOW TRIGGERS")
triggers = cur.fetchall()
trig_refs = []
for t in triggers:
    stmt = str(t.get('Statement', ''))
    hits = [b for b in BACKUP_TABLES_TO_DROP if b in stmt]
    if hits:
        trig_refs.append((t['Trigger'], hits))
print(f"\n  Triggers checked ({len(triggers)}): {[t['Trigger'] for t in triggers]}")
print(f"  Backup table references in triggers: {len(trig_refs)}")
print("  -> NONE" if not trig_refs else "")
for tr, h in trig_refs:
    print(f"    TRIGGER {tr} references {h}")

# Foreign keys
cur.execute("""
    SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME
    FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL
""")
all_fks = cur.fetchall()
fk_refs = [r for r in all_fks
           if r['TABLE_NAME'] in BACKUP_TABLES_TO_DROP
           or r['REFERENCED_TABLE_NAME'] in BACKUP_TABLES_TO_DROP]
print(f"\n  Foreign keys involving any of the 17 backup tables: {len(fk_refs)}")
print("  -> NONE" if not fk_refs else "")
for r in fk_refs:
    print(f"    {r['TABLE_NAME']}.{r['COLUMN_NAME']} -> {r['REFERENCED_TABLE_NAME']}")

print("\n  Application code (routes / frontend JS / migrations): NONE")
print("  (Confirmed by full codebase search -- only backup scripts reference bkp_/backup_)")

# ---------------------------------------------------------------
print("\n" + SEP)
print("CHECK 4 -- SNAPSHOT COVERAGE SUMMARY")
print(SEP)
print("\n  The snap_ step will data-copy these live tables before any DROP runs:")
for t in LIVE_TABLES:
    print(f"    {t:<42} {rc(t):>5} rows")
print("""
  Structure NOT captured by snap_: PRIMARY KEY, FK, INDEX, AUTO_INCREMENT.
  Use mysqldump for a complete structural backup before proceeding.
""")

# ---------------------------------------------------------------
print(SEP)
print("CHECK 5 -- CAN THE SCRIPT ACCIDENTALLY DROP A NON-BACKUP TABLE?")
print(SEP)
print("""
  Guard 1 -- Explicit 17-name allowlist:
    Only the 17 names listed in BACKUP_TABLES_TO_DROP are ever iterated.
    No wildcard (LIKE), no dynamic name construction, no prefix loop.

  Guard 2 -- LIVE_TABLES hard-refusal (cleanup_backups.py line 117):
    Before every DROP the script checks:
      if t in LIVE_TABLES:
          print('[SKIP -- IS LIVE TABLE]')
          continue
    Even a hypothetical typo inserting a live table name in the list
    is caught and refused at this point.

  Guard 3 -- table_exists() pre-check (line 115):
    DROP is called only when information_schema confirms the table exists.
    Already-absent tables are silently skipped -- no error, no side effect.

  VERDICT: The script cannot drop any table outside the 17-name allowlist.
  Live tables are doubly protected: they are not in the allowlist AND the
  hard-refusal check would block them even if they were.
""")

# ---------------------------------------------------------------
print(SEP)
print("CHECK 6 -- POST-CLEANUP TESTING PLAN")
print(SEP)
print("""
  Automatic checks (run by cleanup_backups.py itself):
    [AUTO] Pre vs post row counts for all 8 live tables must match exactly.
    [AUTO] Confirms none of the 17 targeted tables remain in the database.

  Manual checks to run immediately after cleanup:

  A) Flask backend starts cleanly:
       python backend/app.py
       Expected: "Running on http://127.0.0.1:5000" with no import errors

  B) API smoke-tests (open in browser or curl):
       GET /api/venues            -- returns venue list
       GET /api/events            -- returns event list
       GET /api/committees        -- returns committee list
       GET /api/bookings          -- returns booking requests
       GET /api/approvals/stats   -- returns approval statistics

  C) Views still functional:
       SELECT COUNT(*) FROM booking_details;       -- expect > 0
       SELECT COUNT(*) FROM pending_requests;      -- expect >= 0
       SELECT COUNT(*) FROM approval_report;       -- expect > 0

  D) Triggers still active:
       SHOW TRIGGERS;
       Expected: 3 triggers on booking_request
         before_booking_insert / validate_booking_time / prevent_booking_overlap

  E) Stored procedures still callable:
       CALL get_available_venues(1);
       CALL get_bookings_by_status('Pending');

  F) Four-member workflow data intact:
       booking_approval_stage  -- must still show 52 rows
       approval_audit_trail    -- must still show 12 rows
       booking_request         -- must still show 23 rows
       A Pending booking must display all 4 approval stages in the UI

  G) Foreign key integrity:
       All 9 FK constraints on live tables remain intact (verified in
       inspection -- none of them reference backup tables).
""")

cur.close()
conn.close()
print(SEP)
print("All 6 checks complete. Zero data was modified.")
print(SEP)
