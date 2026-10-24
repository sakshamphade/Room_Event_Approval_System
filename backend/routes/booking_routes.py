from flask import Blueprint, jsonify, request
from db import get_db_connection
from routes.auth_routes import get_current_user, require_auth

booking_bp = Blueprint("booking", __name__)

FOUR_STAGES = [
    (1, "Chairperson"),
    (2, "POC"),
    (3, "General Secretary"),
    (4, "College Authority")
]

# GET all booking requests (enriched with current_stage_name and stage summary)
@booking_bp.route("/bookings", methods=["GET"])
def get_bookings():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            request_id, event_id, venue_id, requester_id,
            start_time, end_time, created_at, status,
            current_stage, rejected_by_stage, is_legacy,
            CASE current_stage
                WHEN 1 THEN 'Chairperson'
                WHEN 2 THEN 'POC'
                WHEN 3 THEN 'General Secretary'
                WHEN 4 THEN 'College Authority'
                ELSE 'Completed'
            END AS current_stage_name
        FROM booking_request 
        ORDER BY request_id DESC
    """)
    bookings = cursor.fetchall()

    cursor.close()
    connection.close()
    return jsonify(bookings)


# GET one booking request with stage progress
@booking_bp.route("/bookings/<int:request_id>", methods=["GET"])
def get_booking(request_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            request_id, event_id, venue_id, requester_id,
            start_time, end_time, created_at, status,
            current_stage, rejected_by_stage, is_legacy,
            CASE current_stage
                WHEN 1 THEN 'Chairperson'
                WHEN 2 THEN 'POC'
                WHEN 3 THEN 'General Secretary'
                WHEN 4 THEN 'College Authority'
                ELSE 'Completed'
            END AS current_stage_name
        FROM booking_request 
        WHERE request_id = %s
    """, (request_id,))
    booking = cursor.fetchone()

    if booking is None:
        cursor.close()
        connection.close()
        return jsonify({"message": "Booking request not found"}), 404

    # Fetch all 4 approval stages for this booking
    cursor.execute("""
        SELECT 
            s.stage_id, s.request_id, s.stage_order, s.stage_name, 
            s.status, s.approver_id, u.full_name AS approver_name,
            s.remarks, s.decided_at, s.created_at, s.updated_at
        FROM booking_approval_stage s
        LEFT JOIN user u ON s.approver_id = u.user_id
        WHERE s.request_id = %s
        ORDER BY s.stage_order ASC
    """, (request_id,))
    booking["stages"] = cursor.fetchall()

    cursor.close()
    connection.close()
    return jsonify(booking)


# GET my bookings (requester's own requests)
@booking_bp.route("/bookings/my", methods=["GET"])
def get_my_bookings():
    current_user = get_current_user()
    requester_id = current_user["user_id"] if current_user else 1

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            request_id, event_id, venue_id, requester_id,
            start_time, end_time, created_at, status,
            current_stage, rejected_by_stage, is_legacy,
            CASE current_stage
                WHEN 1 THEN 'Chairperson'
                WHEN 2 THEN 'POC'
                WHEN 3 THEN 'General Secretary'
                WHEN 4 THEN 'College Authority'
                ELSE 'Completed'
            END AS current_stage_name
        FROM booking_request 
        WHERE requester_id = %s
        ORDER BY request_id DESC
    """, (requester_id,))
    bookings = cursor.fetchall()

    cursor.close()
    connection.close()
    return jsonify(bookings)


# CREATE booking request (initializes 4 approval stages atomically)
@booking_bp.route("/bookings", methods=["POST"])
def create_booking():
    data = request.get_json() or {}
    current_user = get_current_user()
    requester_id = current_user["user_id"] if current_user else 1

    if not data.get("event_id") or not data.get("venue_id") or not data.get("start_time") or not data.get("end_time"):
        return jsonify({"message": "Missing required fields (event_id, venue_id, start_time, end_time)"}), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        query_booking = """
            INSERT INTO booking_request
            (event_id, venue_id, requester_id, start_time, end_time, status, current_stage, is_legacy)
            VALUES (%s, %s, %s, %s, %s, 'Pending', 1, 0)
        """
        values_booking = (
            data["event_id"],
            data["venue_id"],
            requester_id,
            data["start_time"],
            data["end_time"]
        )
        cursor.execute(query_booking, values_booking)
        new_request_id = cursor.lastrowid

        # Initialize the 4 approval stages
        query_stage = """
            INSERT INTO booking_approval_stage
            (request_id, stage_order, stage_name, status)
            VALUES (%s, %s, %s, 'Pending')
        """
        for stage_order, stage_name in FOUR_STAGES:
            cursor.execute(query_stage, (new_request_id, stage_order, stage_name))

        connection.commit()

        cursor.close()
        connection.close()
        return jsonify({
            "message": "Booking request created successfully with 4-stage approval workflow initialized",
            "request_id": new_request_id,
            "status": "Pending",
            "current_stage": 1,
            "current_stage_name": "Chairperson"
        }), 201

    except Exception as e:
        connection.rollback()
        cursor.close()
        connection.close()
        # Return trigger signal errors or unexpected database errors
        return jsonify({"message": str(e)}), 400


# UPDATE booking request
@booking_bp.route("/bookings/<int:request_id>", methods=["PUT"])
def update_booking(request_id):
    data = request.get_json() or {}
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Check if booking exists
        cursor.execute("SELECT status, current_stage FROM booking_request WHERE request_id = %s", (request_id,))
        existing = cursor.fetchone()
        if not existing:
            cursor.close()
            connection.close()
            return jsonify({"message": "Booking request not found"}), 404

        # Only allow time/venue edits if still Pending or authorized
        query = """
            UPDATE booking_request
            SET event_id = %s,
                venue_id = %s,
                start_time = %s,
                end_time = %s
            WHERE request_id = %s
        """
        values = (
            data.get("event_id"),
            data.get("venue_id"),
            data.get("start_time"),
            data.get("end_time"),
            request_id
        )
        cursor.execute(query, values)
        connection.commit()

        cursor.close()
        connection.close()
        return jsonify({"message": "Booking request updated successfully"}), 200
    except Exception as e:
        connection.rollback()
        cursor.close()
        connection.close()
        return jsonify({"message": str(e)}), 400


# DELETE booking request
@booking_bp.route("/bookings/<int:request_id>", methods=["DELETE"])
def delete_booking(request_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("DELETE FROM booking_request WHERE request_id = %s", (request_id,))
        connection.commit()

        if cursor.rowcount == 0:
            cursor.close()
            connection.close()
            return jsonify({"message": "Booking request not found"}), 404

        cursor.close()
        connection.close()
        return jsonify({"message": "Booking request deleted successfully"}), 200
    except Exception as e:
        connection.rollback()
        cursor.close()
        connection.close()
        return jsonify({"message": str(e)}), 400