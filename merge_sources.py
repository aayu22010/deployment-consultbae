"""
ConsultBae — Task 1: Merge Script
==================================
Reads 3 source CSV files, cleans and normalizes each field,
deduplicates people across files using email + phone matching,
and writes a unified 'persons' table into consultbae.db (SQLite).

Also logs every data quality issue found (for Task 4) into a
'data_issues' table and prints a summary report.

Usage:
    python merge_sources.py
"""

import csv
import os
import re
import sqlite3
from datetime import datetime
from collections import defaultdict

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE1 = os.path.join(BASE_DIR, "source1_naukri_applicants.csv")
SOURCE2 = os.path.join(BASE_DIR, "source2_gig_workers.csv")
SOURCE3 = os.path.join(BASE_DIR, "source3_cbnexus_contacts.csv")
DB_PATH = os.path.join(BASE_DIR, "consultbae.db")

# ─── Data issue logger ────────────────────────────────────────────────────────
data_issues: list[dict] = []


def log_issue(source: str, row_num: int | None, field: str, issue_type: str,
              original_value: str, fixed_value: str, description: str):
    """Record a data quality issue for the Task 4 report."""
    data_issues.append({
        "source_file": source,
        "row_number": row_num,
        "field": field,
        "issue_type": issue_type,
        "original_value": str(original_value),
        "fixed_value": str(fixed_value),
        "description": description,
    })


# ═══════════════════════════════════════════════════════════════════════════════
#  NORMALIZERS
# ═══════════════════════════════════════════════════════════════════════════════

def normalize_phone(raw: str, source: str = "", row: int | None = None) -> str | None:
    """Strip prefixes/separators → last 10 digits. Returns None if invalid."""
    if not raw or not raw.strip():
        return None
    original = raw.strip()
    digits = re.sub(r"[^0-9]", "", original)
    if len(digits) >= 10:
        normalized = digits[-10:]
        if normalized != original:
            log_issue(source, row, "phone", "format_inconsistency",
                      original, normalized,
                      f"Phone normalized from '{original}' to 10-digit '{normalized}'")
        return normalized
    log_issue(source, row, "phone", "invalid_value",
              original, "", f"Phone '{original}' has fewer than 10 digits")
    return None


# City alias map: maps lowercased variants → canonical name
CITY_ALIASES = {
    "gurgaon": "Gurugram",
    "gurugram": "Gurugram",
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "new delhi": "New Delhi",
    "delhi": "Delhi",
    "delhi ncr": "Delhi NCR",
    "noida": "Noida",
    "pune": "Pune",
}


def normalize_city(raw: str, source: str = "", row: int | None = None) -> str:
    """Trim whitespace, apply alias mapping, title-case."""
    if not raw or not raw.strip():
        return ""
    original = raw.strip()
    key = original.lower()
    canonical = CITY_ALIASES.get(key, original.title())
    if canonical != original:
        log_issue(source, row, "city", "inconsistent_format",
                  original, canonical,
                  f"City normalized from '{original}' to '{canonical}'")
    return canonical


def normalize_email(raw: str, source: str = "", row: int | None = None) -> str | None:
    """Lowercase, strip whitespace. Returns None if empty."""
    if not raw or not raw.strip():
        return None
    original = raw.strip()
    normalized = original.lower()
    if normalized != original:
        log_issue(source, row, "email", "inconsistent_casing",
                  original, normalized,
                  f"Email lowered from '{original}' to '{normalized}'")
    return normalized


def normalize_name(raw: str, source: str = "", row: int | None = None) -> str:
    """Title-case, strip whitespace."""
    if not raw or not raw.strip():
        return ""
    original = raw.strip()
    normalized = original.title()
    if normalized != original:
        log_issue(source, row, "name", "inconsistent_casing",
                  original, normalized,
                  f"Name normalized from '{original}' to '{normalized}'")
    return normalized


def normalize_skills(raw: str, source: str = "", row: int | None = None) -> str:
    """Lowercase, strip each skill, sort, dedupe."""
    if not raw or not raw.strip():
        return ""
    original = raw.strip()
    skills = sorted(set(s.strip().lower() for s in original.split(",") if s.strip()))
    normalized = ", ".join(skills)
    if normalized != original:
        log_issue(source, row, "skills", "inconsistent_format",
                  original, normalized,
                  "Skills normalized (lowercased, sorted, deduped)")
    return normalized


def normalize_ctc(raw: str, source: str = "", row: int | None = None) -> float | None:
    """
    Normalize CTC to lakhs (float).
    - Values <= 100 are assumed to be in lakhs already (e.g. 8.3 → 8.3).
    - Values > 100 are assumed to be raw annual in rupees → divide by 100000.
    """
    if not raw or not raw.strip():
        return None
    original = raw.strip()
    try:
        val = float(original)
    except ValueError:
        log_issue(source, row, "ctc", "invalid_value",
                  original, "", f"CTC '{original}' is not a valid number")
        return None
    if val <= 100:
        # Already in lakhs
        log_issue(source, row, "ctc", "format_inconsistency",
                  original, f"{val:.2f} LPA",
                  f"CTC '{original}' treated as lakhs (≤100)")
        return round(val, 2)
    else:
        # Raw rupees → convert to lakhs
        lakhs = round(val / 100000, 2)
        log_issue(source, row, "ctc", "format_inconsistency",
                  original, f"{lakhs:.2f} LPA",
                  f"CTC '{original}' treated as raw rupees, converted to {lakhs:.2f} LPA")
        return lakhs


def normalize_date(raw: str, source: str = "", row: int | None = None) -> str | None:
    """Parse various date formats → YYYY-MM-DD."""
    if not raw or not raw.strip():
        return None
    original = raw.strip()
    formats = [
        "%Y-%m-%d",        # 2026-08-08
        "%d-%m-%Y",        # 24-07-2026
        "%m/%d/%Y",        # 07/13/2026
        "%d %b %Y",        # 7 Jul 2026, 19 Jul 2026
        "%d %B %Y",        # 7 July 2026
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(original, fmt)
            iso = dt.strftime("%Y-%m-%d")
            if iso != original:
                log_issue(source, row, "applied_date", "format_inconsistency",
                          original, iso,
                          f"Date parsed from '{original}' (format: {fmt}) to '{iso}'")
            return iso
        except ValueError:
            continue

    log_issue(source, row, "applied_date", "invalid_value",
              original, "", f"Date '{original}' could not be parsed with any known format")
    return original  # keep original if unparseable


def normalize_status(raw: str, source: str = "", row: int | None = None) -> str:
    """Lowercase status values."""
    if not raw or not raw.strip():
        return ""
    original = raw.strip()
    normalized = original.lower()
    if normalized != original:
        log_issue(source, row, "status", "inconsistent_casing",
                  original, normalized,
                  f"Status normalized from '{original}' to '{normalized}'")
    return normalized


def normalize_verified(raw: str, source: str = "", row: int | None = None) -> int | None:
    """Convert Y/yes/Yes/N/No → 1 or 0."""
    if not raw or not raw.strip():
        return None
    original = raw.strip()
    key = original.lower()
    if key in ("y", "yes"):
        val = 1
    elif key in ("n", "no"):
        val = 0
    else:
        log_issue(source, row, "verified", "invalid_value",
                  original, "", f"Verified '{original}' not recognized")
        return None
    if original not in ("Y", "N"):
        log_issue(source, row, "verified", "inconsistent_format",
                  original, str(val),
                  f"Verified normalized from '{original}' to {val}")
    return val


def normalize_rate(raw: str, source: str = "", row: int | None = None) -> str | None:
    """Keep rate as-is (string) but log the mixed format issue."""
    if not raw or not raw.strip():
        return None
    original = raw.strip()
    # Detect and log mixed formats
    if "/hr" in original.lower():
        log_issue(source, row, "rate", "mixed_format",
                  original, original,
                  f"Rate is hourly format: '{original}'")
    elif "/month" in original.lower():
        log_issue(source, row, "rate", "mixed_format",
                  original, original,
                  f"Rate is monthly format: '{original}'")
    return original


# ═══════════════════════════════════════════════════════════════════════════════
#  READERS — one per source
# ═══════════════════════════════════════════════════════════════════════════════

def read_source1() -> list[dict]:
    """Read source1_naukri_applicants.csv."""
    records = []
    seen_keys: dict[str, dict] = {}   # "email|phone" -> info dict
    seen_phones: dict[str, dict] = {}  # phone -> info dict

    with open(SOURCE1, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # row 1 is header
            email = normalize_email(row.get("Email", ""), "source1", i)
            phone = normalize_phone(row.get("Phone", ""), "source1", i)

            # -- Detect within-file duplicates by email+phone --
            dup_key = f"{email}|{phone}"
            # Also check by phone alone (catches alt. email variants)
            phone_dup = None
            if phone and phone in seen_phones:
                phone_dup = seen_phones[phone]

            matched_prev = None
            if dup_key in seen_keys:
                matched_prev = seen_keys[dup_key]
            elif phone_dup:
                matched_prev = phone_dup
                log_issue("source1", i, "row", "duplicate_row",
                          f"phone={phone}", f"first seen row {phone_dup['row']}",
                          f"Same phone as row {phone_dup['row']} but different email "
                          f"('{email}' vs '{phone_dup['email']}') — treating as duplicate")

            if matched_prev:
                prev_row = matched_prev["row"]
                prev_name = matched_prev["name"]
                prev_email = matched_prev["email"]
                prev_list_idx = matched_prev["list_idx"]
                curr_name = row.get("Full Name", "").strip()

                if matched_prev is seen_keys.get(dup_key):
                    log_issue("source1", i, "row", "duplicate_row",
                              dup_key, f"first seen row {prev_row}",
                              f"Duplicate of row {prev_row} (same email+phone)")

                # Prefer full name over abbreviated (e.g., 'Rohit Verma' over 'R. Verma')
                if len(curr_name) > len(prev_name):
                    records[prev_list_idx]["full_name"] = normalize_name(curr_name, "source1", i)
                    log_issue("source1", i, "name", "name_upgraded",
                              prev_name, curr_name,
                              f"Upgraded name from '{prev_name}' to '{curr_name}' (fuller version)")

                # Prefer non-alt email over alt. email
                if prev_email and prev_email.startswith("alt.") and email and not email.startswith("alt."):
                    records[prev_list_idx]["email"] = email
                    log_issue("source1", i, "email", "email_upgraded",
                              prev_email, email,
                              f"Upgraded email from '{prev_email}' to '{email}' (non-alt preferred)")

                continue  # skip the duplicate

            seen_keys[dup_key] = {"row": i, "name": row.get("Full Name", "").strip(),
                                  "email": email, "list_idx": len(records)}
            if phone:
                seen_phones[phone] = seen_keys[dup_key]

            # Check for abbreviated name (R. Verma → likely Rohit Verma)
            name_raw = row.get("Full Name", "").strip()
            if re.match(r"^[A-Z]\.\s", name_raw):
                log_issue("source1", i, "name", "abbreviated_name",
                          name_raw, name_raw,
                          f"Name '{name_raw}' appears abbreviated; may be duplicate of full name in another row")

            # Check for 'alt.' email prefix
            if email and email.startswith("alt."):
                log_issue("source1", i, "email", "alternate_email",
                          email, email,
                          f"Email '{email}' has 'alt.' prefix — likely an alternate address")

            rec = {
                "full_name": normalize_name(name_raw, "source1", i),
                "email": email,
                "phone": phone,
                "city": normalize_city(row.get("City", ""), "source1", i),
                "experience_years": None,
                "current_ctc_lakhs": None,
                "applied_date": normalize_date(row.get("Applied Date", ""), "source1", i),
                "skills": normalize_skills(row.get("Skills", ""), "source1", i),
                "gig_rate": None,
                "gig_status": None,
                "is_verified": None,
                "projects_completed": None,
                "sources": ["source1"],
            }

            # Experience
            exp_raw = row.get("Experience (Years)", "").strip()
            if exp_raw:
                try:
                    rec["experience_years"] = round(float(exp_raw), 1)
                except ValueError:
                    log_issue("source1", i, "experience", "invalid_value",
                              exp_raw, "", f"Experience '{exp_raw}' is not a valid number")

            # CTC
            rec["current_ctc_lakhs"] = normalize_ctc(
                row.get("Current CTC", ""), "source1", i)

            records.append(rec)

    print(f"  Source 1: {len(records)} records read (after removing within-file duplicates)")
    return records


def read_source2() -> list[dict]:
    """Read source2_gig_workers.csv — handles blank rows & shifted row."""
    records = []
    seen_emails: dict[str, int] = {}

    with open(SOURCE2, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            raw_email = row.get("email_id", "").strip()
            raw_name = row.get("worker_name", "").strip()

            # ── Detect blank row ──
            if not raw_email and not raw_name:
                log_issue("source2", i, "row", "blank_row",
                          "", "", "Completely blank row in data")
                continue

            # ── Detect shifted/corrupted row ──
            # Heuristic: if the email_id field contains commas or doesn't look
            # like an email, the row is likely shifted
            if raw_email and ("," in raw_email or "@" not in raw_email):
                log_issue("source2", i, "row", "shifted_row",
                          str(dict(row)), "",
                          f"Row appears corrupted/shifted — email_id field contains '{raw_email}'. "
                          "Skipping (data likely duplicated from another row).")
                continue

            email = normalize_email(raw_email, "source2", i)

            # Deduplicate within source2
            if email and email in seen_emails:
                log_issue("source2", i, "row", "duplicate_row",
                          email, f"first seen row {seen_emails[email]}",
                          f"Duplicate email '{email}' — first seen row {seen_emails[email]}")
                continue
            if email:
                seen_emails[email] = i

            rec = {
                "full_name": normalize_name(raw_name, "source2", i),
                "email": email,
                "phone": None,  # source2 has no phone field
                "city": normalize_city(row.get("location", ""), "source2", i),
                "experience_years": None,
                "current_ctc_lakhs": None,
                "applied_date": None,
                "skills": normalize_skills(row.get("skill_tags", ""), "source2", i),
                "gig_rate": normalize_rate(row.get("rate", ""), "source2", i),
                "gig_status": normalize_status(row.get("status", ""), "source2", i),
                "is_verified": None,
                "projects_completed": None,
                "sources": ["source2"],
            }
            records.append(rec)

    print(f"  Source 2: {len(records)} records read (after removing blank/shifted/duplicate rows)")
    return records


def read_source3() -> list[dict]:
    """Read source3_cbnexus_contacts.csv — handles duplicate header row."""
    records = []
    seen_phones: dict[str, int] = {}

    with open(SOURCE3, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            raw_name = row.get("Name", "").strip()
            raw_phone = row.get("Phone Number", "").strip()

            # ── Detect repeated header row ──
            if raw_name == "Name" and raw_phone == "Phone Number":
                log_issue("source3", i, "row", "duplicate_header",
                          str(dict(row)), "",
                          "Duplicate header row in middle of data")
                continue

            phone = normalize_phone(raw_phone, "source3", i)

            # Deduplicate within source3 by name (since there's no email)
            # Use name+phone as the dedup key
            name_norm = normalize_name(raw_name, "source3", i)
            dedup_key = f"{name_norm}|{phone}"

            # Special case: Arjun Mehta appears twice with different phones
            if phone and phone in seen_phones:
                # Different person or data error — log but keep both
                existing_row = seen_phones[phone]
                log_issue("source3", i, "row", "possible_duplicate",
                          f"phone={phone}", f"first seen row {existing_row}",
                          f"Same phone '{phone}' seen in row {existing_row} — could be duplicate")

            if name_norm == "Arjun Mehta" and phone:
                # Check for the known issue: two entries with different phones
                arjun_key = f"Arjun Mehta"
                existing = [r for r in records if r["full_name"] == "Arjun Mehta"]
                if existing:
                    log_issue("source3", i, "row", "ambiguous_duplicate",
                              f"Arjun Mehta with phone {phone}",
                              f"Also in row with phone {existing[0]['phone']}",
                              "Two 'Arjun Mehta' entries with different phones — "
                              "keeping both as potentially different people")

            if phone:
                seen_phones[phone] = i

            # Verified
            verified_raw = row.get("Verified", "").strip()
            is_verified = normalize_verified(verified_raw, "source3", i)

            # Projects completed
            projects_raw = row.get("Projects Completed", "").strip()
            projects = None
            if projects_raw:
                try:
                    projects = int(projects_raw)
                except ValueError:
                    log_issue("source3", i, "projects_completed", "invalid_value",
                              projects_raw, "",
                              f"Projects '{projects_raw}' is not a valid integer")

            rec = {
                "full_name": name_norm,
                "email": None,  # source3 has no email field
                "phone": phone,
                "city": normalize_city(row.get("City", ""), "source3", i),
                "experience_years": None,
                "current_ctc_lakhs": None,
                "applied_date": None,
                "skills": None,
                "gig_rate": None,
                "gig_status": None,
                "is_verified": is_verified,
                "projects_completed": projects,
                "sources": ["source3"],
            }
            records.append(rec)

    print(f"  Source 3: {len(records)} records read (after removing duplicate header)")
    return records


# ═══════════════════════════════════════════════════════════════════════════════
#  MERGE LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

def merge_record(existing: dict, incoming: dict) -> dict:
    """
    Merge 'incoming' into 'existing'. For each field, keep the non-null value.
    If both are non-null, prefer existing (first seen) for most fields,
    but merge skills (union) and sources (append).
    """
    merged = existing.copy()

    # Track sources
    merged["sources"] = list(set(existing.get("sources", []) + incoming.get("sources", [])))

    # For each field, fill in blanks from incoming
    for key in ["full_name", "email", "phone", "city", "experience_years",
                "current_ctc_lakhs", "applied_date", "gig_rate", "gig_status",
                "is_verified", "projects_completed"]:
        if not merged.get(key) and incoming.get(key):
            merged[key] = incoming[key]

    # Merge skills: union of both sets
    s1 = set(s.strip() for s in (existing.get("skills") or "").split(",") if s.strip())
    s2 = set(s.strip() for s in (incoming.get("skills") or "").split(",") if s.strip())
    union = sorted(s1 | s2)
    if union:
        merged["skills"] = ", ".join(union)

    # City conflict logging
    c1 = existing.get("city", "")
    c2 = incoming.get("city", "")
    if c1 and c2 and c1 != c2:
        log_issue(
            ", ".join(incoming["sources"]), None, "city", "cross_source_conflict",
            f"{c1} vs {c2}",
            c1,  # keep existing
            f"City mismatch for '{merged['full_name']}': "
            f"'{c1}' (kept) vs '{c2}' (incoming)"
        )

    return merged


def merge_all(s1_records: list[dict], s2_records: list[dict],
              s3_records: list[dict]) -> list[dict]:
    """
    Merge all records from 3 sources into a unified list.
    Matching keys:
      - email (source1 ↔ source2)
      - phone (source1 ↔ source3)
      - email→phone transitivity (source2 ↔ source3 via source1)
    """
    # Master list of merged records
    master: list[dict] = []

    # Indexes for fast lookup
    email_index: dict[str, int] = {}      # email -> master index
    phone_index: dict[str, int] = {}      # phone -> master index
    name_city_index: dict[str, int] = {}  # "name|city" -> master index (fallback)

    def add_or_merge(record: dict):
        """Add record to master or merge with existing match."""
        email = record.get("email")
        phone = record.get("phone")
        name = record.get("full_name", "")
        city = record.get("city", "")

        match_idx = None

        # Try to find match by email first
        if email and email in email_index:
            match_idx = email_index[email]

        # Try to find match by phone
        if match_idx is None and phone and phone in phone_index:
            match_idx = phone_index[phone]

        # Handle alt. email: also check without 'alt.' prefix
        if match_idx is None and email and email.startswith("alt."):
            base_email = email[4:]  # remove 'alt.' prefix
            if base_email in email_index:
                match_idx = email_index[base_email]
                log_issue(", ".join(record["sources"]), None, "email",
                          "alt_email_merge",
                          email, base_email,
                          f"Merged '{email}' with '{base_email}' (alt. prefix match)")

        # Fallback: match by normalized name + city
        # This catches source2<->source3 records that share no email/phone
        if match_idx is None and name and city:
            nc_key = f"{name.lower()}|{city.lower()}"
            if nc_key in name_city_index:
                match_idx = name_city_index[nc_key]
                log_issue(", ".join(record["sources"]), None, "name+city",
                          "name_city_match",
                          nc_key, f"merged with master[{match_idx}]",
                          f"Matched '{name}' in '{city}' by name+city fallback")

        if match_idx is not None:
            # Merge into existing record
            master[match_idx] = merge_record(master[match_idx], record)
            # Update indexes with any newly-filled fields
            merged = master[match_idx]
            if merged.get("email") and merged["email"] not in email_index:
                email_index[merged["email"]] = match_idx
            if merged.get("phone") and merged["phone"] not in phone_index:
                phone_index[merged["phone"]] = match_idx
            # Update name+city index
            m_name = merged.get("full_name", "")
            m_city = merged.get("city", "")
            if m_name and m_city:
                name_city_index[f"{m_name.lower()}|{m_city.lower()}"] = match_idx
        else:
            # New unique person
            idx = len(master)
            master.append(record)
            if email:
                email_index[email] = idx
            if phone:
                phone_index[phone] = idx
            if name and city:
                name_city_index[f"{name.lower()}|{city.lower()}"] = idx

    # Process in order: source1 first (richest data), then source2, then source3
    print("\n  Merging Source 1 records...")
    for rec in s1_records:
        add_or_merge(rec)
    print(f"    Master size after Source 1: {len(master)}")

    print("  Merging Source 2 records...")
    for rec in s2_records:
        add_or_merge(rec)
    print(f"    Master size after Source 2: {len(master)}")

    print("  Merging Source 3 records...")
    for rec in s3_records:
        add_or_merge(rec)
    print(f"    Master size after Source 3: {len(master)}")

    return master


# ═══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════════════════════════

SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       TEXT NOT NULL,
    email           TEXT,
    phone           TEXT,
    city            TEXT,
    experience_years REAL,
    current_ctc_lakhs REAL,
    applied_date    TEXT,
    skills          TEXT,
    gig_rate        TEXT,
    gig_status      TEXT,
    is_verified     INTEGER,
    projects_completed INTEGER,
    source_files    TEXT
);

CREATE TABLE IF NOT EXISTS data_issues (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT,
    row_number      INTEGER,
    field           TEXT,
    issue_type      TEXT,
    original_value  TEXT,
    fixed_value     TEXT,
    description     TEXT
);
"""


def write_to_db(records: list[dict]):
    """Write merged records + data issues to SQLite."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    # Insert persons
    for rec in records:
        cur.execute("""
            INSERT INTO persons
                (full_name, email, phone, city, experience_years,
                 current_ctc_lakhs, applied_date, skills, gig_rate,
                 gig_status, is_verified, projects_completed, source_files)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rec["full_name"],
            rec.get("email"),
            rec.get("phone"),
            rec.get("city"),
            rec.get("experience_years"),
            rec.get("current_ctc_lakhs"),
            rec.get("applied_date"),
            rec.get("skills"),
            rec.get("gig_rate"),
            rec.get("gig_status"),
            rec.get("is_verified"),
            rec.get("projects_completed"),
            ", ".join(rec.get("sources", [])),
        ))

    # Insert data issues
    for issue in data_issues:
        cur.execute("""
            INSERT INTO data_issues
                (source_file, row_number, field, issue_type,
                 original_value, fixed_value, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            issue["source_file"],
            issue["row_number"],
            issue["field"],
            issue["issue_type"],
            issue["original_value"],
            issue["fixed_value"],
            issue["description"],
        ))

    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  CROSS-CHECK / VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

def cross_check(records: list[dict]):
    """Verify merged DB against source files — spot-check key records."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("\n" + "=" * 70)
    print("  CROSS-CHECK REPORT")
    print("=" * 70)

    total = cur.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
    print(f"\n  Total persons in DB: {total}")

    # Count by source
    for src in ["source1", "source2", "source3"]:
        count = cur.execute(
            "SELECT COUNT(*) FROM persons WHERE source_files LIKE ?",
            (f"%{src}%",)
        ).fetchone()[0]
        print(f"  Persons from {src}: {count}")

    # Persons in multiple sources
    multi = cur.execute(
        "SELECT COUNT(*) FROM persons WHERE source_files LIKE '%,%'"
    ).fetchone()[0]
    print(f"  Persons in multiple sources: {multi}")

    # ── Spot-checks ──
    print("\n  -- Spot-checks --")

    # 1) R. Verma / Rohit Verma should be ONE record
    rohit = cur.execute(
        "SELECT * FROM persons WHERE email = 'rohit.verma13@mailtest.example.org'"
    ).fetchall()
    status = "[PASS]" if len(rohit) == 1 else "[FAIL]"
    print(f"  {status}: R. Verma / Rohit Verma duplicate -> {len(rohit)} record(s) "
          f"(expected 1)")

    # 2) Nikhil Chopra (alt. email) should be ONE record
    nikhil = cur.execute(
        "SELECT * FROM persons WHERE full_name LIKE '%Nikhil Chopra%'"
    ).fetchall()
    status = "[PASS]" if len(nikhil) == 1 else "[FAIL]"
    print(f"  {status}: Nikhil Chopra (alt. email) -> {len(nikhil)} record(s) "
          f"(expected 1)")

    # 3) Isha Chopra (shifted row) should be ONE record
    isha_c = cur.execute(
        "SELECT * FROM persons WHERE full_name = 'Isha Chopra'"
    ).fetchall()
    status = "[PASS]" if len(isha_c) == 1 else "[FAIL]"
    print(f"  {status}: Isha Chopra (shifted row in source2) -> {len(isha_c)} record(s) "
          f"(expected 1)")

    # 4) Tanvi Gupta should appear in all 3 sources
    tanvi = cur.execute(
        "SELECT source_files FROM persons WHERE full_name = 'Tanvi Gupta'"
    ).fetchone()
    if tanvi:
        srcs = tanvi["source_files"]
        count = srcs.count("source")
        status = "[PASS]" if count == 3 else "[FAIL]"
        print(f"  {status}: Tanvi Gupta sources = '{srcs}' (expected all 3)")

    # 5) Two Deepak Nairs in source2 should remain separate
    deepak = cur.execute(
        "SELECT * FROM persons WHERE full_name = 'Deepak Nair'"
    ).fetchall()
    status = "[PASS]" if len(deepak) == 2 else "[CHECK]"
    print(f"  {status}: Deepak Nair (two different people in source2) -> "
          f"{len(deepak)} record(s) (expected 2)")

    # 6) Blank row in source2 should not create a person
    blank = cur.execute(
        "SELECT * FROM persons WHERE full_name = '' OR full_name IS NULL"
    ).fetchall()
    status = "[PASS]" if len(blank) == 0 else "[FAIL]"
    print(f"  {status}: No blank-name records in DB -> {len(blank)} found (expected 0)")

    # 7) No duplicate header as a person from source3
    header_person = cur.execute(
        "SELECT * FROM persons WHERE full_name = 'Name'"
    ).fetchall()
    status = "[PASS]" if len(header_person) == 0 else "[FAIL]"
    print(f"  {status}: No header row as person from source3 -> {len(header_person)} found "
          f"(expected 0)")

    # ── Show all merged persons ──
    print(f"\n  -- All {total} persons in database --")
    print(f"  {'ID':>3} {'Name':<22} {'Email':<42} {'Phone':<12} {'City':<14} {'Sources'}")
    print(f"  {'-'*3} {'-'*22} {'-'*42} {'-'*12} {'-'*14} {'-'*30}")
    for row in cur.execute("SELECT * FROM persons ORDER BY id"):
        print(f"  {row['id']:>3} {(row['full_name'] or ''):<22} "
              f"{(row['email'] or ''):<42} {(row['phone'] or ''):<12} "
              f"{(row['city'] or ''):<14} {row['source_files']}")

    # ── Data issues summary ──
    issue_count = cur.execute("SELECT COUNT(*) FROM data_issues").fetchone()[0]
    print(f"\n  Total data issues logged: {issue_count}")

    # Group by type
    print("\n  -- Issues by type --")
    for row in cur.execute(
        "SELECT issue_type, COUNT(*) as cnt FROM data_issues "
        "GROUP BY issue_type ORDER BY cnt DESC"
    ):
        print(f"    {row[1]:>3}x  {row[0]}")

    # Group by source
    print("\n  -- Issues by source --")
    for row in cur.execute(
        "SELECT source_file, COUNT(*) as cnt FROM data_issues "
        "GROUP BY source_file ORDER BY cnt DESC"
    ):
        print(f"    {row[1]:>3}x  {row[0]}")

    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  ConsultBae — Task 1: Merge Pipeline")
    print("=" * 70)

    # 1. Read & clean
    print("\n[READ] Reading source files...")
    s1 = read_source1()
    s2 = read_source2()
    s3 = read_source3()

    # 2. Merge
    print("\n[MERGE] Merging records...")
    merged = merge_all(s1, s2, s3)

    # 3. Write to DB
    print(f"\n[WRITE] Writing {len(merged)} merged persons to {DB_PATH}...")
    write_to_db(merged)
    print("  Done!")

    # 4. Cross-check
    cross_check(merged)

    print("\n" + "=" * 70)
    print("  Pipeline complete. Database: consultbae.db")
    print("=" * 70)


if __name__ == "__main__":
    main()
