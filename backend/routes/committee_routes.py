from flask import Blueprint, jsonify, request
from db import get_db_connection

committee_bp = Blueprint("committee", __name__)


# GET all committees
@committee_bp.route("/committees", methods=["GET"])
def get_committees():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT * FROM committee ORDER BY committee_id")
    committees = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(committees)


# GET one committee
@committee_bp.route("/committees/<int:committee_id>", methods=["GET"])
def get_committee(committee_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM committee WHERE committee_id = %s",
        (committee_id,)
    )

    committee = cursor.fetchone()

    cursor.close()
    connection.close()

    if committee is None:
        return jsonify({
            "message": "Committee not found"
        }), 404

    return jsonify(committee)


# CREATE committee
@committee_bp.route("/committees", methods=["POST"])
def create_committee():
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        INSERT INTO committee
        (name, advisor, contact_email)
        VALUES (%s, %s, %s)
    """

    values = (
        data["name"],
        data["advisor"],
        data["contact_email"]
    )

    cursor.execute(query, values)
    connection.commit()

    new_id = cursor.lastrowid

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Committee created successfully",
        "committee_id": new_id
    }), 201


# UPDATE committee
@committee_bp.route("/committees/<int:committee_id>", methods=["PUT"])
def update_committee(committee_id):
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        UPDATE committee
        SET name = %s,
            advisor = %s,
            contact_email = %s
        WHERE committee_id = %s
    """

    values = (
        data["name"],
        data["advisor"],
        data["contact_email"],
        committee_id
    )

    cursor.execute(query, values)
    connection.commit()

    if cursor.rowcount == 0:
        cursor.close()
        connection.close()

        return jsonify({
            "message": "Committee not found"
        }), 404

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Committee updated successfully"
    }), 200

# DELETE committee
@committee_bp.route("/committees/<int:committee_id>", methods=["DELETE"])
def delete_committee(committee_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM committee WHERE committee_id = %s",
        (committee_id,)
    )

    connection.commit()

    if cursor.rowcount == 0:
        cursor.close()
        connection.close()

        return jsonify({
            "message": "Committee not found"
        }), 404

    cursor.close()
    connection.close()

    return jsonify({
        "message": "Committee deleted successfully"
    }), 200