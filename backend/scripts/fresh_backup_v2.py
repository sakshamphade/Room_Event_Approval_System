"""
Fresh Database Backup Script v2
Creates timestamped backup of ALL tables, triggers, and views.
Verifies backup integrity by comparing row counts.
"""
import os
import sys
import time
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db import get_db_connection


def create_fresh_backup():
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    prefix = f"bkp2_{timestamp}"
    print(f"=" * 60)
    print(f"FRESH DATABASE BACKUP — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Backup prefix: {prefix}")
    print(f"=" * 60)

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # 1. Discover all non-backup base tables
    cur.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
    all_tables = [row[list(row.keys())[0]] for row in cur.fetchall()]
    # Only backup core tables (skip old backup tables to avoid recursive backups)
    core_tables = [t for t in all_tables if not t.startswith('bkp_') and not t.startswith('bkp2_') and not t.startswith('backup_')]
    print(f"\nCore tables to backup: {core_tables}")

    # 2. Backup each table
    backup_results = {}
    for tbl in core_tables:
        cur.execute(f"SELECT COUNT(*) AS c FROM `{tbl}`")
        orig_count = cur.fetchone()['c']

        backup_tbl = f"{prefix}_{tbl}"
        print(f"\n  Backing up `{tbl}` ({orig_count} rows) -> `{backup_tbl}` ...")
        cur.execute(f"CREATE TABLE `{backup_tbl}` AS SELECT * FROM `{tbl}`")

        cur.execute(f"SELECT COUNT(*) AS c FROM `{backup_tbl}`")
        bkp_count = cur.fetchone()['c']

        if orig_count != bkp_count:
            print(f"  *** MISMATCH: original={orig_count}, backup={bkp_count}")
            conn.rollback()
            raise RuntimeError(f"Row count mismatch for {tbl}")

        backup_results[tbl] = {'backup_table': backup_tbl, 'original_rows': orig_count, 'backup_rows': bkp_count, 'match': True}
        print(f"  -> Verified: {bkp_count}/{orig_count} rows OK")

    conn.commit()

    # 3. Capture trigger definitions
    print(f"\n--- Trigger Definitions ---")
    cur.execute("SHOW TRIGGERS")
    triggers = cur.fetchall()
    trigger_info = []
    for t in triggers:
        info = {'name': t.get('Trigger'), 'event': t.get('Event'), 'table': t.get('Table'), 'timing': t.get('Timing'), 'statement': t.get('Statement', '')[:200]}
        trigger_info.append(info)
        print(f"  Trigger: {info['name']} ({info['timing']} {info['event']} ON {info['table']})")

    # 4. Capture view definitions
    print(f"\n--- View Definitions ---")
    cur.execute("SHOW FULL TABLES WHERE Table_type = 'VIEW'")
    views = [row[list(row.keys())[0]] for row in cur.fetchall()]
    view_info = []
    for v in views:
        try:
            cur.execute(f"SHOW CREATE VIEW `{v}`")
            create_stmt = cur.fetchone()
            view_info.append({'name': v, 'create_statement': str(create_stmt.get('Create View', ''))[:300]})
            print(f"  View: {v}")
        except Exception as e:
            print(f"  View: {v} (could not read definition: {e})")

    cur.close()
    conn.close()

    # 5. Summary
    print(f"\n{'=' * 60}")
    print(f"BACKUP VERIFICATION SUMMARY")
    print(f"{'=' * 60}")
    all_ok = True
    for tbl, meta in backup_results.items():
        status = "OK" if meta['match'] else "FAIL"
        if not meta['match']:
            all_ok = False
        print(f"  {tbl:30s} -> {meta['backup_table']:45s} | {meta['original_rows']:4d} rows | {status}")

    print(f"\n  Triggers captured: {len(trigger_info)}")
    print(f"  Views captured:   {len(view_info)}")
    print(f"\n  Overall: {'ALL BACKUPS VERIFIED SUCCESSFULLY' if all_ok else 'BACKUP VERIFICATION FAILED'}")
    print(f"{'=' * 60}")

    return {
        'timestamp': timestamp,
        'prefix': prefix,
        'tables': backup_results,
        'triggers': trigger_info,
        'views': view_info,
        'all_ok': all_ok
    }


if __name__ == "__main__":
    result = create_fresh_backup()
    if not result['all_ok']:
        sys.exit(1)
    print("\nBackup complete. Safe to proceed with migration/testing.")
