from flask import Blueprint, jsonify, request
from db import get_db_connection
from routes.auth_routes import get_current_user

approval_bp = Blueprint("approval", __name__)

STAGE_ORDER_MAP = {
    "Chairperson": 1,
    "POC": 2,
    "General Secretary": 3,
    "College Authority": 4
}

STAGE_NAMES = {
    1: "Chairperson",
    2: "POC",
    3: "General Secretary",
    4: "College Authority"
}

# -----------------------------------------------------------------------------
# 1. GET requests awaiting the current approver's decision
# -----------------------------------------------------------------------------
@approval_bp.route("/approvals/pending", methods=["GET"])
def get_pending_for_current_user():
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Authentication required"}), 401

    if current_user["user_type"] != "APPROVAL_USER":
        return jsonify([]), 200

    approver_role = current_user.get("approval_role")
    required_stage = STAGE_ORDER_MAP.get(approver_role)
    if not required_stage:
        return jsonify([]), 200

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # A booking is awaiting this approver if:
    # - booking_request.status = 'Pending'
    # - booking_request.current_stage = required_stage
    # - the stage itself in booking_approval_stage is 'Pending'
    cur.execute("""
        SELECT 
            br.request_id,
            br.event_id,
            e.event_name,
            e.event_date,
            e.expected_attendees,
            c.name AS committee_name,
            br.venue_id,
            v.venue_name,
            v.location,
            v.capacity,
            br.start_time,
            br.end_time,
            br.created_at AS requested_at,
            br.status,
            br.current_stage,
            s.stage_name AS current_stage_name,
            br.requester_id,
            u.full_name AS requester_name,
            u.email AS requester_email
        FROM booking_request br
        JOIN event e ON br.event_id = e.event_id
        JOIN committee c ON e.committee_id = c.committee_id
        JOIN venue v ON br.venue_id = v.venue_id
        JOIN booking_approval_stage s ON br.request_id = s.request_id AND s.stage_order = br.current_stage
        LEFT JOIN user u ON br.requester_id = u.user_id
        WHERE br.status = 'Pending' 
          AND br.current_stage = %s
          AND s.status = 'Pending'
        ORDER BY br.request_id ASC
    """, (required_stage,))
    pending_items = cur.fetchall()

    cur.close()
    conn.close()
    return jsonify(pending_items)


# -----------------------------------------------------------------------------
# 2. GET summary cards stats for approval dashboard
# -----------------------------------------------------------------------------
@approval_bp.route("/approvals/stats", methods=["GET"])
def get_approval_stats():
    current_user = get_current_user()
    approver_role = current_user.get("approval_role") if current_user else None
    user_id = current_user.get("user_id") if current_user else None
    required_stage = STAGE_ORDER_MAP.get(approver_role) if approver_role else None

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # Total booking requests
    cur.execute("SELECT COUNT(*) AS c FROM booking_request")
    total_requests = cur.fetchone()["c"]

    # Fully approved
    cur.execute("SELECT COUNT(*) AS c FROM booking_request WHERE status = 'Approved'")
    fully_approved = cur.fetchone()["c"]

    # Awaiting my approval
    awaiting_my_approval = 0
    if required_stage:
        cur.execute("""
            SELECT COUNT(*) AS c 
            FROM booking_request br
            JOIN booking_approval_stage s ON br.request_id = s.request_id AND s.stage_order = br.current_stage
            WHERE br.status = 'Pending' AND br.current_stage = %s AND s.status = 'Pending'
        """, (required_stage,))
        awaiting_my_approval = cur.fetchone()["c"]

    # Approved by me
    approved_by_me = 0
    if user_id:
        cur.execute("SELECT COUNT(*) AS c FROM booking_approval_stage WHERE approver_id = %s AND status = 'Approved'", (user_id,))
        approved_by_me = cur.fetchone()["c"]

    # Rejected by me
    rejected_by_me = 0
    if user_id:
        cur.execute("SELECT COUNT(*) AS c FROM booking_approval_stage WHERE approver_id = %s AND status = 'Rejected'", (user_id,))
        rejected_by_me = cur.fetchone()["c"]

    cur.close()
    conn.close()

    return jsonify({
        "total_requests": total_requests,
        "awaiting_my_approval": awaiting_my_approval,
        "approved_by_me": approved_by_me,
        "rejected_by_me": rejected_by_me,
        "fully_approved": fully_approved
    })


# -----------------------------------------------------------------------------
# 3. GET approval progress & stages for a specific booking
# -----------------------------------------------------------------------------
@approval_bp.route("/approvals/booking/<int:request_id>/progress", methods=["GET"])
def get_booking_approval_progress(request_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT 
            br.request_id, br.status, br.current_stage, br.rejected_by_stage, br.is_legacy,
            e.event_name, c.name AS committee_name, v.venue_name, v.capacity,
            br.start_time, br.end_time, br.requester_id,
            u.full_name AS requester_name
        FROM booking_request br
        JOIN event e ON br.event_id = e.event_id
        JOIN committee c ON e.committee_id = c.committee_id
        JOIN venue v ON br.venue_id = v.venue_id
        LEFT JOIN user u ON br.requester_id = u.user_id
        WHERE br.request_id = %s
    """, (request_id,))
    booking = cur.fetchone()

    if not booking:
        cur.close()
        conn.close()
        return jsonify({"message": "Booking request not found"}), 404

    cur.execute("""
        SELECT 
            s.stage_id, s.stage_order, s.stage_name, s.status,
            s.approver_id, u.full_name AS approver_name,
            s.remarks, s.decided_at, s.created_at, s.updated_at
        FROM booking_approval_stage s
        LEFT JOIN user u ON s.approver_id = u.user_id
        WHERE s.request_id = %s
        ORDER BY s.stage_order ASC
    """, (request_id,))
    stages = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({
        "booking": booking,
        "stages": stages
    })


# -----------------------------------------------------------------------------
# 4. SUBMIT approval decision (Chairperson -> POC -> GenSec -> Authority)
# -----------------------------------------------------------------------------
@approval_bp.route("/approvals/decide", methods=["POST"])
def submit_approval_decision():
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Authentication required. Please log in."}), 401

    if current_user["user_type"] != "APPROVAL_USER":
        return jsonify({"error": "Booking users cannot access approval decision endpoints."}), 403

    user_role = current_user.get("approval_role")
    user_id = current_user["user_id"]
    user_name = current_user.get("full_name", user_role)

    required_stage_order = STAGE_ORDER_MAP.get(user_role)
    if not required_stage_order:
        return jsonify({"error": f"Invalid approver role '{user_role}'."}), 403

    data = request.get_json() or {}
    request_id = data.get("request_id")
    decision = data.get("decision")  # "Approved" or "Rejected"
    remarks = (data.get("remarks") or "").strip()

    if not request_id or not decision:
        return jsonify({"error": "request_id and decision ('Approved' or 'Rejected') are required."}), 400

    if decision not in ["Approved", "Rejected"]:
        return jsonify({"error": "Decision must be 'Approved' or 'Rejected'."}), 400

    if decision == "Rejected" and not remarks:
        return jsonify({"error": "A meaningful rejection reason/remarks is required when rejecting a request."}), 400

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    try:
        conn.start_transaction()

        # Lock booking_request row
        cur.execute("""
            SELECT request_id, status, current_stage, requester_id, rejected_by_stage 
            FROM booking_request 
            WHERE request_id = %s 
            FOR UPDATE
        """, (request_id,))
        booking = cur.fetchone()

        if not booking:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({"error": f"Booking request #{request_id} not found."}), 404

        # 1. Requester cannot approve their own booking
        if booking.get("requester_id") == user_id:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({"error": "Requesters are not permitted to approve or reject their own booking requests."}), 403

        # 2. Check overall booking status
        if booking["status"] == "Rejected":
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({"error": f"Booking request #{request_id} was already rejected and cannot be acted upon."}), 400

        if booking["status"] == "Approved":
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({"error": f"Booking request #{request_id} is already fully approved."}), 400

        # 3. Check sequential workflow order
        current_booking_stage = booking["current_stage"]

        if current_booking_stage < required_stage_order:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({
                "error": f"Out-of-order action: Stage {STAGE_NAMES.get(current_booking_stage)} must approve before {user_role} can act."
            }), 400

        if current_booking_stage > required_stage_order:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({
                "error": f"Stage {user_role} has already been completed for booking #{request_id}."
            }), 400

        # 4. Fetch the target stage row
        cur.execute("""
            SELECT stage_id, stage_order, stage_name, status 
            FROM booking_approval_stage 
            WHERE request_id = %s AND stage_order = %s 
            FOR UPDATE
        """, (request_id, required_stage_order))
        stage_row = cur.fetchone()

        if not stage_row:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({"error": f"Stage record for {user_role} not found."}), 404

        if stage_row["status"] != "Pending":
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({"error": f"Stage {user_role} has already been decided ({stage_row['status']}). Duplicate decisions are rejected."}), 400

        # 5. Verify all prior stages are Approved
        if required_stage_order > 1:
            cur.execute("""
                SELECT COUNT(*) AS c 
                FROM booking_approval_stage 
                WHERE request_id = %s AND stage_order < %s AND status != 'Approved'
            """, (request_id, required_stage_order))
            unapproved_prior = cur.fetchone()["c"]
            if unapproved_prior > 0:
                conn.rollback()
                cur.close()
                conn.close()
                return jsonify({"error": "Cannot act early. Previous approval stages are not approved."}), 400

        # 6. Apply Decision
        prev_overall_status = booking["status"]
        if decision == "Rejected":
            new_stage_status = "Rejected"
            new_overall_status = "Rejected"
            next_stage = current_booking_stage
            rejected_by = user_role
        else: # Approved
            new_stage_status = "Approved"
            if required_stage_order == 4:
                # College Authority is final stage!
                new_overall_status = "Approved"
                next_stage = 5  # Completed
                rejected_by = None
            else:
                new_overall_status = "Pending"
                next_stage = current_booking_stage + 1
                rejected_by = None

        # Update stage
        cur.execute("""
            UPDATE booking_approval_stage
            SET status = %s,
                approver_id = %s,
                remarks = %s,
                decided_at = CURRENT_TIMESTAMP
            WHERE stage_id = %s
        """, (new_stage_status, user_id, remarks, stage_row["stage_id"]))

        # Update booking_request
        cur.execute("""
            UPDATE booking_request
            SET status = %s,
                current_stage = %s,
                rejected_by_stage = %s
            WHERE request_id = %s
        """, (new_overall_status, next_stage, rejected_by, request_id))

        # Also write into audit trail
        cur.execute("""
            INSERT INTO approval_audit_trail
            (request_id, approver_role, decision, remarks, decided_by_id, decided_by_name, previous_status, new_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            request_id,
            user_role,
            decision,
            remarks,
            user_id,
            user_name,
            prev_overall_status,
            new_overall_status
        ))

        # Backward compatibility: write legacy approval row
        cur.execute("""
            INSERT INTO approval
            (request_id, decision, remarks)
            VALUES (%s, %s, %s)
        """, (request_id, decision, f"[{user_role}] {remarks}"))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "message": f"Successfully recorded {decision} by {user_role}.",
            "request_id": request_id,
            "stage_name": user_role,
            "decision": decision,
            "new_overall_status": new_overall_status,
            "current_stage": next_stage,
            "is_fully_approved": (new_overall_status == "Approved")
        }), 200

    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"error": f"Failed to submit decision: {str(e)}"}), 500


# -----------------------------------------------------------------------------
# 5. GET Audit Trail
# -----------------------------------------------------------------------------
@approval_bp.route("/approvals/audit-trail", methods=["GET"])
def get_audit_trail():
    request_id = request.args.get("request_id")
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    if request_id:
        cur.execute("""
            SELECT 
                audit_id, request_id, approver_role, decision, remarks,
                decided_by_id, decided_by_name, previous_status, new_status, decided_at
            FROM approval_audit_trail
            WHERE request_id = %s
            ORDER BY audit_id DESC
        """, (request_id,))
    else:
        cur.execute("""
            SELECT 
                audit_id, request_id, approver_role, decision, remarks,
                decided_by_id, decided_by_name, previous_status, new_status, decided_at
            FROM approval_audit_trail
            ORDER BY audit_id DESC
            LIMIT 200
        """)

    trails = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(trails)


# -----------------------------------------------------------------------------
# 6. Legacy / Approvals Compatibility Endpoints
# -----------------------------------------------------------------------------
@approval_bp.route("/approvals", methods=["GET"])
def get_approvals():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM approval ORDER BY approval_id DESC")
    approvals = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(approvals)


@approval_bp.route("/approvals/<int:approval_id>", methods=["GET"])
def get_approval(approval_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM approval WHERE approval_id = %s", (approval_id,))
    approval = cur.fetchone()
    cur.close()
    conn.close()
    if approval is None:
        return jsonify({"message": "Approval not found"}), 404
    return jsonify(approval)


@approval_bp.route("/approvals", methods=["POST"])
def create_legacy_approval():
    # If called directly from old code, redirect logic through decide endpoint
    return submit_approval_decision()


@approval_bp.route("/approvals/<int:approval_id>", methods=["PUT"])
def update_legacy_approval(approval_id):
    return jsonify({"message": "Approval decisions are immutable once submitted to the audit trail."}), 403


@approval_bp.route("/approvals/<int:approval_id>", methods=["DELETE"])
def delete_legacy_approval(approval_id):
    return jsonify({"message": "Approval records cannot be deleted. Audit history is preserved."}), 403