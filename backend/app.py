"""Phit backend: a tiny local Flask app for browsing Garmin runs and
comparing two of them side by side.

Run with: python app.py
Then open http://localhost:5000
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

import garmin_client as gc

load_dotenv()

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
session = gc.GarminSession()


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/api/status")
def status():
    return jsonify({"connected": session.connected, "display_name": session.display_name})


@app.post("/api/connect")
def connect():
    body = request.get_json(silent=True) or {}
    result = session.connect(email=body.get("email"), password=body.get("password"))
    status_code = 200 if result["status"] in ("connected", "mfa_required") else 401
    return jsonify(result), status_code


@app.post("/api/connect/mfa")
def connect_mfa():
    body = request.get_json(silent=True) or {}
    code = (body.get("code") or "").strip()
    if not code:
        return jsonify({"status": "error", "message": "MFA code is required"}), 400
    result = session.submit_mfa(code)
    status_code = 200 if result["status"] == "connected" else 401
    return jsonify(result), status_code


@app.get("/api/runs")
def runs():
    if not session.connected:
        return jsonify({"message": "Not connected"}), 409
    limit = request.args.get("limit", default=20, type=int)
    try:
        return jsonify(gc.list_recent_runs(session, limit=limit))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"message": str(exc)}), 502


@app.get("/api/runs/<activity_id>")
def run_detail(activity_id: str):
    if not session.connected:
        return jsonify({"message": "Not connected"}), 409
    try:
        return jsonify(gc.get_run_detail(session, activity_id))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"message": str(exc)}), 502


@app.get("/api/compare")
def compare():
    if not session.connected:
        return jsonify({"message": "Not connected"}), 409
    id_a = request.args.get("a")
    id_b = request.args.get("b")
    if not id_a or not id_b:
        return jsonify({"message": "Query params 'a' and 'b' (activity ids) are required"}), 400
    try:
        return jsonify(gc.compare_runs(session, id_a, id_b))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"message": str(exc)}), 502


if __name__ == "__main__":
    app.run(debug=True, port=5000)
