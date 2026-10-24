from flask import Blueprint, jsonify, request
from db import get_db_connection

venue_bp = Blueprint("venue", __name__)


# GET all venues
@venue_bp.route("/venues", methods=["GET"])
def get_venues():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT * FROM venue ORDER BY venue_id")
    venues = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(venues)


# GET one venue
@venue_bp.route("/venues/<int:venue_id>", methods=["GET"])
def get_venue(venue_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM venue WHERE venue_id = %s",
        (venue_id,)
    )

    venue = cursor.fetchone()

    cursor.close()
    connection.close()

    if venue is None:
        return jsonify({
            "message": "Venue not found"
        }), 404

    return jsonify(venue)


# CREATE venue
@venue_bp.route("/venues", methods=["POST"])
def create_venue():
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        INSERT INTO venue
        (venue_name, venue_type, location, capacity)
        VALUES (%s, %s, %s, %s)
    """

    values = (
        data["venue_name"],
        data["venue_type"],
        data["location"],
        data["capacity"]
    )

    cursor.execute(query, values)
    connection.commit()

    new_id = cursor.lastrowid

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Venue created successfully",
        "venue_id": new_id
    }), 201


# UPDATE venue
@venue_bp.route("/venues/<int:venue_id>", methods=["PUT"])
def update_venue(venue_id):
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        UPDATE venue
        SET venue_name = %s,
            venue_type = %s,
            location = %s,
            capacity = %s
        WHERE venue_id = %s
    """

    values = (
        data["venue_name"],
        data["venue_type"],
        data["location"],
        data["capacity"],
        venue_id
    )

    cursor.execute(query, values)
    connection.commit()

    if cursor.rowcount == 0:
        cursor.close()
        connection.close()

        return jsonify({
            "message": "Venue not found"
        }), 404

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Venue updated successfully"
    }), 200


# DELETE venue
@venue_bp.route("/venues/<int:venue_id>", methods=["DELETE"])
def delete_venue(venue_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM venue WHERE venue_id = %s",
        (venue_id,)
    )

    connection.commit()

    if cursor.rowcount == 0:
        cursor.close()
        connection.close()

        return jsonify({
            "message": "Venue not found"
        }), 404

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Venue deleted successfully"
    }), 200