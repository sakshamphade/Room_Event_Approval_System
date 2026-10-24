from flask import Blueprint, jsonify, request
from db import get_db_connection

event_bp = Blueprint("event", __name__)


# GET all events
@event_bp.route("/events", methods=["GET"])
def get_events():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT * FROM event ORDER BY event_id")
    events = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(events)


# GET one event
@event_bp.route("/events/<int:event_id>", methods=["GET"])
def get_event(event_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM event WHERE event_id = %s",
        (event_id,)
    )

    event = cursor.fetchone()

    cursor.close()
    connection.close()

    if event is None:
        return jsonify({
            "message": "Event not found"
        }), 404

    return jsonify(event)


# CREATE event
@event_bp.route("/events", methods=["POST"])
def create_event():
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        INSERT INTO event
        (event_name, event_date, expected_attendees, committee_id)
        VALUES (%s, %s, %s, %s)
    """

    values = (
        data["event_name"],
        data["event_date"],
        data["expected_attendees"],
        data["committee_id"]
    )

    cursor.execute(query, values)
    connection.commit()

    new_id = cursor.lastrowid

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Event created successfully",
        "event_id": new_id
    }), 201


# UPDATE event
@event_bp.route("/events/<int:event_id>", methods=["PUT"])
def update_event(event_id):
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        UPDATE event
        SET event_name = %s,
            event_date = %s,
            expected_attendees = %s,
            committee_id = %s
        WHERE event_id = %s
    """

    values = (
        data["event_name"],
        data["event_date"],
        data["expected_attendees"],
        data["committee_id"],
        event_id
    )

    cursor.execute(query, values)
    connection.commit()

    if cursor.rowcount == 0:
        cursor.close()
        connection.close()

        return jsonify({
            "message": "Event not found"
        }), 404

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Event updated successfully"
    }), 200


# DELETE event
@event_bp.route("/events/<int:event_id>", methods=["DELETE"])
def delete_event(event_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM event WHERE event_id = %s",
        (event_id,)
    )

    connection.commit()

    if cursor.rowcount == 0:
        cursor.close()
        connection.close()

        return jsonify({
            "message": "Event not found"
        }), 404

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Event deleted successfully"
    }), 200