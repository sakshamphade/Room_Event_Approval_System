import os
from flask import Flask, jsonify
from flask_cors import CORS

from routes.committee_routes import committee_bp
from routes.venue_routes import venue_bp
from routes.event_routes import event_bp
from routes.booking_routes import booking_bp
from routes.approval_routes import approval_bp
from routes.auth_routes import auth_bp

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

# Enable CORS with credentials support so sessions work smoothly across frontend and backend
CORS(app, supports_credentials=True, origins=["*"])

app.register_blueprint(committee_bp)
app.register_blueprint(venue_bp)
app.register_blueprint(event_bp)
app.register_blueprint(booking_bp)
app.register_blueprint(approval_bp)
app.register_blueprint(auth_bp, url_prefix="/api")

@app.route("/")
def home():
    return jsonify({
        "message": "Room & Event-Area Approval System API is running",
        "workflow": "Four-Member Approval (Chairperson -> POC -> General Secretary -> College Authority)",
        "version": "3.0.0"
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)