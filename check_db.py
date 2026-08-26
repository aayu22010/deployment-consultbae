"""Quick verification of all tables and audio submissions."""
import sqlite3

conn = sqlite3.connect("consultbae.db")
conn.row_factory = sqlite3.Row

# List all tables
tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()]
print(f"Tables: {tables}")

# Persons count
p_count = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
print(f"Persons: {p_count}")

# Data issues count
d_count = conn.execute("SELECT COUNT(*) FROM data_issues").fetchone()[0]
print(f"Data issues: {d_count}")

# Audio submissions
try:
    subs = conn.execute("SELECT * FROM audio_submissions").fetchall()
    print(f"Audio submissions: {len(subs)}")
    for r in subs:
        print(f"  #{r['id']} {r['name']} ({r['phone']}) - "
              f"{r['original_filename']} - "
              f"dur={r['duration_seconds']}s, "
              f"rate={r['sample_rate_khz']}kHz, "
              f"bitrate={r['bitrate_kbps']}kbps, "
              f"loudness={r['loudness_db']}dB, "
              f"noise={r['noise_estimate']}, "
              f"person_id={r['person_id']}")
except Exception as e:
    print(f"Audio table not yet created (will be created on first app.py run): {e}")

conn.close()
