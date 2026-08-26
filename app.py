"""
ConsultBae - Task 3: Mini Audio Collection App
===============================================
Flask backend that serves the audio submission/listing UI,
handles file uploads, analyzes audio, and stores everything
in the same consultbae.db from Task 1.

Usage:
    python app.py
"""

import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone

from flask import (Flask, request, jsonify, send_from_directory,
                   render_template)

from audio_analyzer import analyze_audio

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "consultbae.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB max upload

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".webm", ".m4a", ".flac", ".aac"}


# ── Database setup ────────────────────────────────────────────────────────────

def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_audio_table():
    """Create the audio_submissions table if it doesn't exist."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audio_submissions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id           INTEGER,
            name                TEXT NOT NULL,
            phone               TEXT NOT NULL,
            filename            TEXT NOT NULL,
            original_filename   TEXT,
            file_size_bytes     INTEGER,
            duration_seconds    REAL,
            sample_rate_khz     REAL,
            bitrate_kbps        REAL,
            loudness_db         REAL,
            noise_estimate      TEXT,
            submitted_at        TEXT,
            FOREIGN KEY (person_id) REFERENCES persons(id)
        )
    """)
    conn.commit()
    conn.close()


def normalize_phone(raw: str) -> str:
    """Strip phone to last 10 digits (same logic as merge script)."""
    digits = re.sub(r"[^0-9]", "", raw.strip())
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def find_person_by_phone(phone: str):
    """Look up a person in the persons table by normalized phone."""
    conn = get_db()
    person = conn.execute(
        "SELECT id, full_name FROM persons WHERE phone = ?", (phone,)
    ).fetchone()
    conn.close()
    return person


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main single-page app."""
    return render_template("index.html")


@app.route("/api/submit", methods=["POST"])
def submit_audio():
    """
    Accept audio submission.
    Expects multipart form: name, phone, audio (file).
    """
    # Validate inputs
    name = request.form.get("name", "").strip()
    phone_raw = request.form.get("phone", "").strip()

    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not phone_raw:
        return jsonify({"error": "Phone number is required"}), 400

    audio_file = request.files.get("audio")
    if not audio_file or audio_file.filename == "":
        return jsonify({"error": "Audio file is required"}), 400

    # Validate extension
    original_filename = audio_file.filename
    ext = os.path.splitext(original_filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": f"Unsupported file type '{ext}'. "
                     f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        }), 400

    # Normalize phone
    phone = normalize_phone(phone_raw)
    if len(phone) < 10:
        return jsonify({"error": "Phone number must have at least 10 digits"}), 400

    # Save file with unique name
    unique_name = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, unique_name)
    audio_file.save(filepath)

    file_size = os.path.getsize(filepath)

    # Analyze audio
    print(f"  Analyzing audio: {original_filename} ({file_size} bytes)...")
    props = analyze_audio(filepath)
    print(f"  -> Duration: {props['duration_seconds']}s, "
          f"Rate: {props['sample_rate_khz']}kHz, "
          f"Bitrate: {props['bitrate_kbps']}kbps, "
          f"Loudness: {props['loudness_db']}dB, "
          f"Noise: {props['noise_estimate']}")

    # Look up person in DB
    person = find_person_by_phone(phone)
    person_id = person["id"] if person else None
    if person:
        print(f"  -> Matched to person: {person['full_name']} (ID {person['id']})")
    else:
        print(f"  -> No existing person found for phone {phone}")

    # Store in database
    submitted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    cur = conn.execute("""
        INSERT INTO audio_submissions
            (person_id, name, phone, filename, original_filename,
             file_size_bytes, duration_seconds, sample_rate_khz,
             bitrate_kbps, loudness_db, noise_estimate, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        person_id, name, phone, unique_name, original_filename,
        file_size, props["duration_seconds"], props["sample_rate_khz"],
        props["bitrate_kbps"], props["loudness_db"],
        props["noise_estimate"], submitted_at,
    ))
    submission_id = cur.lastrowid
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "submission_id": submission_id,
        "person_matched": person["full_name"] if person else None,
        "properties": props,
    }), 201


@app.route("/api/submissions", methods=["GET"])
def list_submissions():
    """Return all audio submissions as JSON."""
    conn = get_db()
    rows = conn.execute("""
        SELECT
            a.id, a.name, a.phone, a.original_filename,
            a.file_size_bytes, a.duration_seconds, a.sample_rate_khz,
            a.bitrate_kbps, a.loudness_db, a.noise_estimate,
            a.submitted_at, a.filename,
            p.full_name as matched_person
        FROM audio_submissions a
        LEFT JOIN persons p ON a.person_id = p.id
        ORDER BY a.id DESC
    """).fetchall()
    conn.close()

    submissions = []
    for row in rows:
        submissions.append({
            "id": row["id"],
            "name": row["name"],
            "phone": row["phone"],
            "original_filename": row["original_filename"],
            "file_size_bytes": row["file_size_bytes"],
            "duration_seconds": row["duration_seconds"],
            "sample_rate_khz": row["sample_rate_khz"],
            "bitrate_kbps": row["bitrate_kbps"],
            "loudness_db": row["loudness_db"],
            "noise_estimate": row["noise_estimate"],
            "submitted_at": row["submitted_at"],
            "audio_url": f"/audio/{row['filename']}",
            "matched_person": row["matched_person"],
        })

    return jsonify(submissions)


@app.route("/audio/<filename>")
def serve_audio(filename):
    """Serve uploaded audio files for playback."""
    return send_from_directory(UPLOAD_DIR, filename)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_audio_table()
    print("=" * 60)
    print("  ConsultBae Audio Collection App")
    print(f"  Database: {DB_PATH}")
    print(f"  Uploads:  {UPLOAD_DIR}")
    print("  Open:     http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True, host="127.0.0.1", port=5000)
