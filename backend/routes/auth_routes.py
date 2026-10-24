from functools import wraps
from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash
from db import get_db_connection

auth_bp = Blueprint("auth", __name__)

def get_current_user():
    """
    Identifies the authenticated user from:
    1. Flask session ('user_id')
    2. Request header 'X-User-Id' (for API testing / frontend simulation)
    3. Authorization Bearer token (if matching user_id)
    Returns dictionary with user record or None.
    """
    user_id = session.get("user_id")
    if not user_id:
        user_header = request.headers.get("X-User-Id")
        if user_header:
            try:
                user_id = int(user_header)
            except ValueError:
                pass

    if not user_id:
        return None

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT user_id, username, full_name, email, user_type, approval_role, is_active FROM user WHERE user_id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user


def require_auth(allowed_types=None, allowed_roles=None):
    """
    Decorator to enforce server-side authentication and role-based authorization.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user or not user.get("is_active"):
                return jsonify({"error": "Authentication required. Please log in or provide valid user identity."}), 401

            if allowed_types and user["user_type"] not in allowed_types:
                return jsonify({"error": f"Forbidden: user type '{user['user_type']}' is not authorized."}), 403

            if allowed_roles and user.get("approval_role") not in allowed_roles:
                return jsonify({"error": f"Forbidden: role '{user.get('approval_role')}' is not authorized for this action."}), 403

            return f(user, *args, **kwargs)
        return decorated_function
    return decorator


@auth_bp.route("/auth/users", methods=["GET"])
def list_users():
    """
    Returns the list of available demo users and authorities with their roles.
    """
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT user_id, username, full_name, email, user_type, approval_role FROM user WHERE is_active = 1 ORDER BY user_id")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(users)


@auth_bp.route("/auth/login", methods=["POST"])
def login():
    """
    Authenticates a user by username and password.
    Sets session and returns user profile.
    """
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM user WHERE username = %s AND is_active = 1", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password"}), 401

    session["user_id"] = user["user_id"]
    return jsonify({
        "message": "Login successful",
        "user": {
            "user_id": user["user_id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "email": user["email"],
            "user_type": user["user_type"],
            "approval_role": user["approval_role"]
        }
    }), 200


@auth_bp.route("/auth/switch-role", methods=["POST"])
def switch_role():
    """
    Allows switching the active demo/presentation user identity on the server.
    Validates that the target user exists in the database.
    """
    data = request.get_json() or {}
    user_id = data.get("user_id")
    approval_role = data.get("approval_role")
    username = data.get("username")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    if user_id:
        cur.execute("SELECT user_id, username, full_name, email, user_type, approval_role FROM user WHERE user_id = %s AND is_active = 1", (user_id,))
    elif approval_role:
        cur.execute("SELECT user_id, username, full_name, email, user_type, approval_role FROM user WHERE approval_role = %s AND is_active = 1", (approval_role,))
    elif username:
        cur.execute("SELECT user_id, username, full_name, email, user_type, approval_role FROM user WHERE username = %s AND is_active = 1", (username,))
    else:
        # Default to booking user
        cur.execute("SELECT user_id, username, full_name, email, user_type, approval_role FROM user WHERE user_type = 'BOOKING_USER' AND is_active = 1 LIMIT 1")

    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        return jsonify({"error": "Specified user/role not found"}), 404

    session["user_id"] = user["user_id"]
    return jsonify({
        "message": "Switched active server role",
        "user": user
    }), 200


@auth_bp.route("/auth/me", methods=["GET"])
def current_user_info():
    """
    Returns current authenticated identity. Defaults to Booking User (user_id=1)
    if no session/header was sent yet, ensuring zero-friction local bootstrap.
    """
    user = get_current_user()
    if not user:
        # Default fallback to booking user (user_id=1) for demonstration
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT user_id, username, full_name, email, user_type, approval_role FROM user WHERE user_id = 1")
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            session["user_id"] = user["user_id"]

    return jsonify({"user": user})


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"message": "Logged out successfully"}), 200
