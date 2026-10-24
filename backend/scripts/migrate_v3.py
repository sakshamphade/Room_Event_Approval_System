import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db import get_db_connection

def run_migration_v3():
    print("=" * 60)
    print("Running Four-Member Approval Workflow Migration (v3)")
    print("=" * 60)
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    try:
        # 1. Add requester_id to booking_request if not exists
        print("\n1. Checking requester_id on booking_request...")
        cur.execute("SHOW COLUMNS FROM booking_request LIKE 'requester_id'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE booking_request ADD COLUMN requester_id INT DEFAULT 1")
            print("   -> Added column `requester_id` to booking_request with default 1.")
        else:
            print("   -> Column `requester_id` already exists.")

        # Check and add foreign key constraint if not present
        cur.execute("""
            SELECT CONSTRAINT_NAME 
            FROM information_schema.KEY_COLUMN_USAGE 
            WHERE TABLE_NAME = 'booking_request' 
              AND COLUMN_NAME = 'requester_id' 
              AND REFERENCED_TABLE_NAME = 'user'
        """)
        if not cur.fetchone():
            cur.execute("""
                ALTER TABLE booking_request 
                ADD CONSTRAINT fk_booking_requester 
                FOREIGN KEY (requester_id) REFERENCES user (user_id)
            """)
            print("   -> Added foreign key fk_booking_requester.")
        else:
            print("   -> Foreign key fk_booking_requester already exists.")

        # 2. Add updated_at to booking_approval_stage if not exists
        print("\n2. Checking updated_at on booking_approval_stage...")
        cur.execute("SHOW COLUMNS FROM booking_approval_stage LIKE 'updated_at'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE booking_approval_stage ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
            print("   -> Added column `updated_at` to booking_approval_stage.")
        else:
            print("   -> Column `updated_at` already exists.")

        # 3. Create approval_audit_trail table if not exists
        print("\n3. Creating approval_audit_trail table if not exists...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS approval_audit_trail (
            audit_id INT AUTO_INCREMENT PRIMARY KEY,
            request_id INT NOT NULL,
            approver_role VARCHAR(50) NOT NULL,
            decision VARCHAR(20) NOT NULL,
            remarks VARCHAR(255) NULL,
            decided_by_id INT NULL,
            decided_by_name VARCHAR(100) NULL,
            previous_status VARCHAR(20) NOT NULL,
            new_status VARCHAR(20) NOT NULL,
            decided_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_audit_request FOREIGN KEY (request_id) REFERENCES booking_request (request_id) ON DELETE CASCADE,
            CONSTRAINT fk_audit_user FOREIGN KEY (decided_by_id) REFERENCES user (user_id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        print("   -> approval_audit_trail verified.")

        # 4. Update view booking_details to include requester details
        print("\n4. Updating booking_details view...")
        cur.execute("""
        CREATE OR REPLACE VIEW booking_details AS
        SELECT 
            br.request_id,
            br.requester_id,
            u.full_name AS requester_name,
            u.email AS requester_email,
            e.event_id,
            e.event_name,
            e.event_date,
            e.expected_attendees,
            c.committee_id,
            c.name AS committee_name,
            v.venue_id,
            v.venue_name,
            v.location,
            v.capacity,
            br.start_time,
            br.end_time,
            br.created_at,
            br.status,
            br.current_stage,
            br.rejected_by_stage,
            br.is_legacy
        FROM booking_request br
        JOIN event e ON br.event_id = e.event_id
        JOIN committee c ON e.committee_id = c.committee_id
        JOIN venue v ON br.venue_id = v.venue_id
        LEFT JOIN user u ON br.requester_id = u.user_id
        """)
        print("   -> booking_details view updated with requester information.")

        conn.commit()
        print("\n" + "=" * 60)
        print("Migration v3 Completed Successfully!")
        print("=" * 60)
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration v3 failed: {e}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_migration_v3()
