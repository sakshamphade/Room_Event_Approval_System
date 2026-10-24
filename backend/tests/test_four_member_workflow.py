import unittest
import json
import os
import sys

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from db import get_db_connection

class TestFourMemberApprovalWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.conn = get_db_connection()
        cls.cur = cls.conn.cursor(dictionary=True)

    @classmethod
    def tearDownClass(cls):
        cls.cur.close()
        cls.conn.close()

    def get_test_venue_and_event(self):
        # Pick an active venue and event
        self.cur.execute("SELECT venue_id FROM venue LIMIT 1")
        venue_id = self.cur.fetchone()["venue_id"]
        self.cur.execute("SELECT event_id FROM event LIMIT 1")
        event_id = self.cur.fetchone()["event_id"]
        return venue_id, event_id

    def test_01_booking_user_creates_request_and_initializes_4_stages(self):
        venue_id, event_id = self.get_test_venue_and_event()
        # Booking User creates request
        res = self.client.post("/bookings", 
            headers={"X-User-Id": "1"}, # User 1: booking_user
            json={
                "event_id": event_id,
                "venue_id": venue_id,
                "start_time": "2026-12-01 09:00:00",
                "end_time": "2026-12-01 12:00:00"
            }
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        req_id = data["request_id"]
        self.assertEqual(data["status"], "Pending")
        self.assertEqual(data["current_stage"], 1)

        # Verify in DB: 4 stages initialized
        self.conn.commit()
        self.cur.execute("SELECT stage_order, stage_name, status FROM booking_approval_stage WHERE request_id = %s ORDER BY stage_order", (req_id,))
        stages = self.cur.fetchall()
        self.assertEqual(len(stages), 4)
        self.assertEqual(stages[0]["stage_name"], "Chairperson")
        self.assertEqual(stages[1]["stage_name"], "POC")
        self.assertEqual(stages[2]["stage_name"], "General Secretary")
        self.assertEqual(stages[3]["stage_name"], "College Authority")
        for s in stages:
            self.assertEqual(s["status"], "Pending")

        # Clean up test row
        self.client.delete(f"/bookings/{req_id}")

    def test_02_sequential_approval_from_chairperson_to_final_approval(self):
        venue_id, event_id = self.get_test_venue_and_event()
        # 1. Create booking
        res = self.client.post("/bookings", 
            headers={"X-User-Id": "1"},
            json={
                "event_id": event_id,
                "venue_id": venue_id,
                "start_time": "2026-12-02 10:00:00",
                "end_time": "2026-12-02 13:00:00"
            }
        )
        req_id = res.get_json()["request_id"]

        # 2. Check Chairperson pending queue (User 2)
        res = self.client.get("/approvals/pending", headers={"X-User-Id": "2"})
        self.assertEqual(res.status_code, 200)
        pending_ids = [item["request_id"] for item in res.get_json()]
        self.assertIn(req_id, pending_ids)

        # 3. Chairperson approves
        res = self.client.post("/approvals/decide",
            headers={"X-User-Id": "2"},
            json={"request_id": req_id, "decision": "Approved", "remarks": "Chairperson approved"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["current_stage"], 2)
        self.assertEqual(res.get_json()["new_overall_status"], "Pending")

        # 4. Check POC pending queue (User 3)
        res = self.client.get("/approvals/pending", headers={"X-User-Id": "3"})
        self.assertEqual(res.status_code, 200)
        pending_ids = [item["request_id"] for item in res.get_json()]
        self.assertIn(req_id, pending_ids)

        # 5. POC approves
        res = self.client.post("/approvals/decide",
            headers={"X-User-Id": "3"},
            json={"request_id": req_id, "decision": "Approved", "remarks": "POC Council approved"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["current_stage"], 3)
        self.assertEqual(res.get_json()["new_overall_status"], "Pending")

        # 6. General Secretary approves (User 4)
        res = self.client.post("/approvals/decide",
            headers={"X-User-Id": "4"},
            json={"request_id": req_id, "decision": "Approved", "remarks": "GenSec approved"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["current_stage"], 4)
        self.assertEqual(res.get_json()["new_overall_status"], "Pending")

        # 7. College Authority approves (User 5 - Final)
        res = self.client.post("/approvals/decide",
            headers={"X-User-Id": "5"},
            json={"request_id": req_id, "decision": "Approved", "remarks": "College Dean final approval"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["new_overall_status"], "Approved")
        self.assertTrue(data["is_fully_approved"])

        # Check DB status
        self.conn.commit()
        self.cur.execute("SELECT status, current_stage FROM booking_request WHERE request_id = %s", (req_id,))
        b = self.cur.fetchone()
        self.assertEqual(b["status"], "Approved")
        self.assertEqual(b["current_stage"], 5)

        # Clean up
        self.client.delete(f"/bookings/{req_id}")

    def test_03_rejection_at_stage_stops_workflow(self):
        venue_id, event_id = self.get_test_venue_and_event()
        # Create booking
        res = self.client.post("/bookings", 
            headers={"X-User-Id": "1"},
            json={
                "event_id": event_id,
                "venue_id": venue_id,
                "start_time": "2026-12-03 14:00:00",
                "end_time": "2026-12-03 17:00:00"
            }
        )
        req_id = res.get_json()["request_id"]

        # Chairperson approves (Stage 1 -> 2)
        self.client.post("/approvals/decide",
            headers={"X-User-Id": "2"},
            json={"request_id": req_id, "decision": "Approved", "remarks": "OK"}
        )

        # POC rejects (Stage 2)
        res = self.client.post("/approvals/decide",
            headers={"X-User-Id": "3"},
            json={"request_id": req_id, "decision": "Rejected", "remarks": "Council schedule conflict"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["new_overall_status"], "Rejected")

        # General Secretary tries to approve rejected request -> Must be rejected
        res = self.client.post("/approvals/decide",
            headers={"X-User-Id": "4"},
            json={"request_id": req_id, "decision": "Approved", "remarks": "Attempting after rejection"}
        )
        self.assertEqual(res.status_code, 400)

        # Clean up
        self.client.delete(f"/bookings/{req_id}")

    def test_04_later_approver_cannot_act_early(self):
        venue_id, event_id = self.get_test_venue_and_event()
        res = self.client.post("/bookings", 
            headers={"X-User-Id": "1"},
            json={
                "event_id": event_id,
                "venue_id": venue_id,
                "start_time": "2026-12-04 10:00:00",
                "end_time": "2026-12-04 13:00:00"
            }
        )
        req_id = res.get_json()["request_id"]

        # College Authority (User 5, Stage 4) tries to approve when stage is 1
        res = self.client.post("/approvals/decide",
            headers={"X-User-Id": "5"},
            json={"request_id": req_id, "decision": "Approved", "remarks": "Premature approval"}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Out-of-order action", res.get_json()["error"])

        # Clean up
        self.client.delete(f"/bookings/{req_id}")

    def test_05_booking_user_cannot_submit_decision(self):
        venue_id, event_id = self.get_test_venue_and_event()
        res = self.client.post("/bookings", 
            headers={"X-User-Id": "1"},
            json={
                "event_id": event_id,
                "venue_id": venue_id,
                "start_time": "2026-12-05 10:00:00",
                "end_time": "2026-12-05 13:00:00"
            }
        )
        req_id = res.get_json()["request_id"]

        # Booking user (User 1) calls /approvals/decide
        res = self.client.post("/approvals/decide",
            headers={"X-User-Id": "1"},
            json={"request_id": req_id, "decision": "Approved", "remarks": "Self approval"}
        )
        self.assertEqual(res.status_code, 403)

        # Clean up
        self.client.delete(f"/bookings/{req_id}")

    def test_06_cannot_approve_twice_at_same_stage(self):
        venue_id, event_id = self.get_test_venue_and_event()
        res = self.client.post("/bookings", 
            headers={"X-User-Id": "1"},
            json={
                "event_id": event_id,
                "venue_id": venue_id,
                "start_time": "2026-12-06 10:00:00",
                "end_time": "2026-12-06 13:00:00"
            }
        )
        req_id = res.get_json()["request_id"]

        # Chairperson approves
        res = self.client.post("/approvals/decide",
            headers={"X-User-Id": "2"},
            json={"request_id": req_id, "decision": "Approved", "remarks": "First approval"}
        )
        self.assertEqual(res.status_code, 200)

        # Chairperson tries to approve again
        res = self.client.post("/approvals/decide",
            headers={"X-User-Id": "2"},
            json={"request_id": req_id, "decision": "Approved", "remarks": "Duplicate approval"}
        )
        self.assertEqual(res.status_code, 400)

        # Clean up
        self.client.delete(f"/bookings/{req_id}")

    def test_07_rejection_requires_meaningful_remarks(self):
        venue_id, event_id = self.get_test_venue_and_event()
        res = self.client.post("/bookings", 
            headers={"X-User-Id": "1"},
            json={
                "event_id": event_id,
                "venue_id": venue_id,
                "start_time": "2026-12-07 10:00:00",
                "end_time": "2026-12-07 13:00:00"
            }
        )
        req_id = res.get_json()["request_id"]

        # Chairperson rejects with empty remarks
        res = self.client.post("/approvals/decide",
            headers={"X-User-Id": "2"},
            json={"request_id": req_id, "decision": "Rejected", "remarks": ""}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("rejection reason", res.get_json()["error"].lower())

        # Clean up
        self.client.delete(f"/bookings/{req_id}")

    def test_08_audit_trail_recorded_accurately(self):
        venue_id, event_id = self.get_test_venue_and_event()
        res = self.client.post("/bookings", 
            headers={"X-User-Id": "1"},
            json={
                "event_id": event_id,
                "venue_id": venue_id,
                "start_time": "2026-12-08 10:00:00",
                "end_time": "2026-12-08 13:00:00"
            }
        )
        req_id = res.get_json()["request_id"]

        # Chairperson approves with unique remarks
        test_remarks = "Unique test remarks for audit audit_check_123"
        self.client.post("/approvals/decide",
            headers={"X-User-Id": "2"},
            json={"request_id": req_id, "decision": "Approved", "remarks": test_remarks}
        )

        # Check audit trail endpoint
        res = self.client.get(f"/approvals/audit-trail?request_id={req_id}")
        self.assertEqual(res.status_code, 200)
        trails = res.get_json()
        self.assertTrue(len(trails) >= 1)
        self.assertEqual(trails[0]["approver_role"], "Chairperson")
        self.assertEqual(trails[0]["remarks"], test_remarks)

        # Clean up
        self.client.delete(f"/bookings/{req_id}")

    def test_09_existing_crud_endpoints_remain_operational(self):
        # Committees
        res = self.client.get("/committees")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(len(res.get_json()) > 0)

        # Venues
        res = self.client.get("/venues")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(len(res.get_json()) > 0)

        # Events
        res = self.client.get("/events")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(len(res.get_json()) > 0)

        # Bookings
        res = self.client.get("/bookings")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(len(res.get_json()) > 0)

if __name__ == "__main__":
    unittest.main()
