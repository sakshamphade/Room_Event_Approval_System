import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db import get_db_connection

def create_fresh_backup():
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    print(f"Creating fresh database backup with timestamp suffix: {timestamp}")
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    tables_to_backup = [
        'booking_request',
        'approval',
        'booking_approval_stage',
        'user',
        'event',
        'venue',
        'committee'
    ]
    
    backup_meta = {}
    
    try:
        for tbl in tables_to_backup:
            cur.execute(f"SHOW TABLES LIKE '{tbl}'")
            if cur.fetchone():
                cur.execute(f"SELECT COUNT(*) AS c FROM {tbl}")
                orig_count = cur.fetchone()['c']
                
                backup_tbl = f"bkp_{timestamp}_{tbl}"
                print(f"Backing up table `{tbl}` ({orig_count} rows) -> `{backup_tbl}`...")
                cur.execute(f"CREATE TABLE `{backup_tbl}` AS SELECT * FROM `{tbl}`")
                
                # Verify backup row count matches exactly
                cur.execute(f"SELECT COUNT(*) AS c FROM `{backup_tbl}`")
                bkp_count = cur.fetchone()['c']
                
                assert orig_count == bkp_count, f"Count mismatch for {tbl}: orig {orig_count} vs backup {bkp_count}"
                backup_meta[tbl] = {'backup_table': backup_tbl, 'rows': orig_count}
                print(f"  -> Verified: {bkp_count} rows copied accurately to `{backup_tbl}`.")
        
        conn.commit()
        print("\nAll fresh backup tables successfully created and verified!")
        for tbl, meta in backup_meta.items():
            print(f" - {tbl}: {meta['rows']} rows -> {meta['backup_table']}")
        return backup_meta
    except Exception as e:
        conn.rollback()
        print(f"Backup failed: {e}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    create_fresh_backup()
