"""
cleanup_backups.py
==================
Step 1 – Takes a fresh timestamped snapshot of all LIVE tables.
Step 2 – Verifies the snapshot row counts match the live tables exactly.
Step 3 – Drops all 17 confirmed-safe backup tables using explicit names.
Step 4 – Verifies live tables are untouched (row counts unchanged).

Safety guarantees:
  • Only tables starting with bkp_ / bkp2_ / backup_ are targeted.
  • Live table names are hardcoded and never touched.
  • If any snapshot row-count mismatch is found, the script aborts before
    executing a single DROP.
  • FK checks are NOT disabled — backup tables have no FKs so none needed.
  • The script is idempotent: re-running after partial completion is safe.
"""

import sys, time
sys.path.insert(0, 'backend')
from db import get_db_connection

LIVE_TABLES = [
    'approval',
    'approval_audit_trail',
    'booking_approval_stage',
    'booking_request',
    'committee',
    'event',
    'user',
    'venue',
]

BACKUP_TABLES_TO_DROP = [
    # Manual / ad-hoc
    'backup_approval',
    'backup_booking_request',
    # Snapshot 1 — 2026-10-13 01:41:35
    'bkp_20261013_014135_approval',
    'bkp_20261013_014135_booking_approval_stage',
    'bkp_20261013_014135_booking_request',
    'bkp_20261013_014135_committee',
    'bkp_20261013_014135_event',
    'bkp_20261013_014135_user',
    'bkp_20261013_014135_venue',
    # Snapshot 2 — 2026-10-13 18:32:36
    'bkp2_20261013_183236_approval',
    'bkp2_20261013_183236_approval_audit_trail',
    'bkp2_20261013_183236_booking_approval_stage',
    'bkp2_20261013_183236_booking_request',
    'bkp2_20261013_183236_committee',
    'bkp2_20261013_183236_event',
    'bkp2_20261013_183236_user',
    'bkp2_20261013_183236_venue',
]


def row_count(cur, table):
    cur.execute(f"SELECT COUNT(*) AS c FROM `{table}`")
    return cur.fetchone()['c']


def table_exists(cur, table):
    cur.execute(
        "SELECT COUNT(*) AS c FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
        (table,)
    )
    return cur.fetchone()['c'] > 0


def run():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # ── PRE-DELETION: capture live row counts ─────────────────
    print("=" * 65)
    print("PRE-DELETION LIVE TABLE ROW COUNTS")
    print("=" * 65)
    pre_counts = {}
    for t in LIVE_TABLES:
        pre_counts[t] = row_count(cur, t)
        print(f"  {t:<45} {pre_counts[t]:>5} rows")

    # ── STEP 1: Create fresh safety snapshot ─────────────────
    ts = time.strftime('%Y%m%d_%H%M%S')
    snapshot_prefix = f"snap_{ts}"
    print(f"\n{'='*65}")
    print(f"STEP 1 — CREATING SAFETY SNAPSHOT (prefix: {snapshot_prefix})")
    print(f"{'='*65}")

    snapshot_counts = {}
    for t in LIVE_TABLES:
        snap = f"{snapshot_prefix}_{t}"
        cur.execute(f"CREATE TABLE `{snap}` AS SELECT * FROM `{t}`")
        snap_c = row_count(cur, snap)
        snapshot_counts[t] = snap_c
        match = "OK" if snap_c == pre_counts[t] else "MISMATCH"
        print(f"  {t:<40} -> {snap_c} rows  [{match}]")
        if match != "OK":
            conn.rollback()
            print("\n[ABORT] Snapshot row count mismatch. No backup tables deleted.")
            sys.exit(1)

    conn.commit()
    print("\n  All snapshot row counts verified. Snapshot committed.")

    # ── STEP 2: Drop backup tables ────────────────────────────
    print(f"\n{'='*65}")
    print("STEP 2 — DROPPING BACKUP TABLES")
    print(f"{'='*65}")

    dropped = []
    skipped = []
    for t in BACKUP_TABLES_TO_DROP:
        if table_exists(cur, t):
            # Safety: refuse if name is also a live table (should never happen)
            if t in LIVE_TABLES:
                print(f"  [SKIP — IS LIVE TABLE] {t}")
                skipped.append(t)
                continue
            cur.execute(f"DROP TABLE `{t}`")
            conn.commit()
            dropped.append(t)
            print(f"  [DROPPED] {t}")
        else:
            skipped.append(t)
            print(f"  [NOT FOUND — already gone] {t}")

    # ── STEP 3: Verify live tables untouched ──────────────────
    print(f"\n{'='*65}")
    print("STEP 3 — POST-DELETION LIVE TABLE VERIFICATION")
    print(f"{'='*65}")
    print(f"{'Table':<45} {'Before':>7} {'After':>7} {'Status':>10}")
    print("-" * 72)

    all_ok = True
    for t in LIVE_TABLES:
        after = row_count(cur, t)
        status = "OK" if after == pre_counts[t] else "CHANGED!"
        if status != "OK":
            all_ok = False
        print(f"  {t:<43} {pre_counts[t]:>7} {after:>7} {status:>10}")

    # ── STEP 4: Confirm no backup tables remain ───────────────
    print(f"\n{'='*65}")
    print("STEP 4 — CONFIRM NO TARGETED BACKUP TABLES REMAIN")
    print(f"{'='*65}")
    remaining = [t for t in BACKUP_TABLES_TO_DROP if table_exists(cur, t)]
    if remaining:
        print(f"  Still present ({len(remaining)}):  {remaining}")
    else:
        print("  All targeted backup tables successfully removed.")

    # ── Summary ───────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("SUMMARY")
    print(f"{'='*65}")
    print(f"  Safety snapshot prefix : {snapshot_prefix}")
    print(f"  Tables dropped         : {len(dropped)}")
    print(f"  Tables not found       : {len([s for s in skipped if s not in LIVE_TABLES])}")
    print(f"  Live data integrity    : {'ALL OK' if all_ok else 'WARNING — ROW COUNT CHANGED'}")

    cur.close()
    conn.close()

    if not all_ok:
        print("\n[WARNING] Live row counts changed unexpectedly. Investigate immediately.")
        sys.exit(1)
    else:
        print("\nCleanup complete. Live application tables are fully intact.")


if __name__ == "__main__":
    run()
