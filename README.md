# ConsultBae — Final Walkthrough

## Quick Start Guide

**1. Clone the repository**
```bash
git clone https://github.com/aayu22010/ConsultBae-AI-Automation-Assignment.git
cd ConsultBae-AI-Automation-Assignment

```

**2. Set up a virtual environment**

```bash
python -m venv venv

# For Windows:
.\venv\Scripts\Activate.ps1
# For Mac/Linux:
source venv/bin/activate

```

**3. Install dependencies**

```bash
pip install -r requirements.txt

```

*(Note: No API keys are required locally, as the LLM automation triggers via a Make.com webhook).*

**4. Run the pipeline and app**
Execute the following commands in order to test the end-to-end flow:

```bash
# Step 1: Run the merge pipeline to build consultbae.db
python merge_sources.py

# Step 2: (Optional) Validate the database creation
python check_db.py

# Step 3: Run the LLM auto-tagging automation
python auto_tag.py

# Step 4: Start the Flask audio app
python app.py

```

After starting `app.py`, open **http://127.0.0.1:5000** in your browser to test the audio collection interface.


## Overview

| Task | Status | Description |
|------|--------|-------------|
| **Task 1** — Merge | **Done** | Python script merging 3 CSVs into unified SQLite DB |
| **Task 2** — Automation | **Done** |	Low-code automation flow exported as task2_make_flow.json |
| **Task 3** — Audio App | **Done** | Flask web app for audio recording/upload with analysis |
| **Task 4** — Data Issues | **Done** | 348 issues logged across 15 categories |

---

## Task 1 — Merge Pipeline

### File: [merge_sources.py](file:///c:/Users/aayus/Desktop/consultbae%20claude/merge_sources.py)

**What it does:**
1. Reads all 3 source CSVs (no external dependencies — uses only Python stdlib)
2. Normalizes every field: phone (10-digit), email (lowercase), city (alias mapping), CTC (to lakhs), dates (to ISO), skills (lowercase+sorted), status, verified
3. Deduplicates within each source file (catches duplicate rows, shifted/corrupted rows, blank rows, repeated headers)
4. Merges across sources using a **3-tier matching strategy**:
   - **Email** (source1 ↔ source2)
   - **Phone** (source1 ↔ source3, transitively source2 ↔ source3)
   - **Name + City** fallback (source2 ↔ source3 where no email/phone overlap)
5. Smart dedup preferences: fuller names over abbreviated, non-alt emails over alt. prefix
6. Writes to `consultbae.db` with `persons` and `data_issues` tables
7. Runs 7 automated cross-checks

### Database: [consultbae.db](file:///c:/Users/aayus/Desktop/consultbae%20claude/consultbae.db)

**Schema:**
```sql
persons (id, full_name, email, phone, city, experience_years,
         current_ctc_lakhs, applied_date, skills, gig_rate,
         gig_status, is_verified, projects_completed, source_files)

data_issues (id, source_file, row_number, field, issue_type,
             original_value, fixed_value, description)

audio_submissions (id, person_id, name, phone, filename,
                   original_filename, file_size_bytes, duration_seconds,
                   sample_rate_khz, bitrate_kbps, loudness_db,
                   noise_estimate, submitted_at)
```

### Results

| Metric | Value |
|--------|-------|
| Total unique persons | **54** |
| From source1 (Naukri) | 40 |
| From source2 (Gig Workers) | 30 |
| From source3 (CBNexus) | 29 |
| Persons in 2+ sources | **29** |
| Data issues logged | **348** |

### Cross-Check (All PASS)

| # | Check | Result |
|---|-------|--------|
| 1 | R. Verma / Rohit Verma merged, name upgraded | PASS |
| 2 | Nikhil Chopra (alt. email) merged, email upgraded | PASS |
| 3 | Isha Chopra (shifted row in source2) → 1 record | PASS |
| 4 | Tanvi Gupta appears in all 3 sources | PASS |
| 5 | Two Deepak Nairs remain separate (different people) | PASS |
| 6 | No blank-name records | PASS |
| 7 | No header-as-person from source3 | PASS |

---

## Task 3 — Mini Audio Collection App

### Files Created

| File | Purpose |
|------|---------|
| [app.py](file:///c:/Users/aayus/Desktop/consultbae%20claude/app.py) | Flask backend — routes for submit, list, serve audio |
| [audio_analyzer.py](file:///c:/Users/aayus/Desktop/consultbae%20claude/audio_analyzer.py) | Audio property extraction (no ffmpeg needed) |
| [templates/index.html](file:///c:/Users/aayus/Desktop/consultbae%20claude/templates/index.html) | Single-page frontend (dark theme, two tabs) |

### How to Run
```bash
python app.py
# Open http://127.0.0.1:5000
```

### Features

**Submit Tab:**
- Name + phone number form
- **Record audio** in browser (MediaRecorder API → WAV conversion)
  - Live waveform visualization during recording
  - Timer display
- **Upload audio** file (WAV, MP3, OGG, WebM, M4A, FLAC — drag & drop)
- Audio preview with playback before submitting
- Matches submitter to existing person in DB by phone number

**Submissions Tab:**
- Lists all submissions with native audio player (play button)
- Shows extracted properties per submission:
  - **Duration** (seconds)
  - **Sample Rate** (kHz)
  - **Bitrate** (kbps)
  - **Loudness** (dBFS via RMS)
  - **Quality/Noise estimate** (clean / moderate / noisy — via spectral flatness)
- "Matched" badge when person found in DB
- Refresh button

### Audio Analysis (no ffmpeg)
- WAV files: Python `wave` module + `numpy` for loudness/noise
- Non-WAV files: `mutagen` for metadata extraction
- Noise estimation uses spectral flatness (geometric/arithmetic mean of power spectrum)

### Screenshots

````carousel
![Submit Audio tab — name/phone form, record button, upload toggle](file:///C:/Users/aayus/.gemini/antigravity-ide/brain/b3063b51-5e17-4648-ac5a-d53b994f911b/audio_collection_main_1787254452288.png)
<!-- slide -->
![Submissions tab — audio entry with play button and extracted properties](file:///C:/Users/aayus/.gemini/antigravity-ide/brain/b3063b51-5e17-4648-ac5a-d53b994f911b/submissions_view_1787255087639.png)
````

---

## Task 4 — Data Issues Report

### Summary: 348 issues across 15 categories

| Issue Type | Count | Description |
|------------|-------|-------------|
| `inconsistent_format` | 138 | Skills casing, city casing, verified values |
| `format_inconsistency` | 118 | Phone prefixes, date formats, CTC units |
| `inconsistent_casing` | 40 | Email ALL-CAPS, name ALL-CAPS, status casing |
| `mixed_format` | 30 | Rate hourly vs monthly (`1415/hr` vs `15k/month`) |
| `name_city_match` | 6 | Source2↔Source3 matched by name+city fallback |
| `cross_source_conflict` | 6 | City mismatch for same person across sources |
| `duplicate_row` | 2 | Within-source exact duplicates |
| `shifted_row` | 1 | Source2 row 20 — columns misaligned |
| `name_upgraded` | 1 | `R. Verma` → `Rohit Verma` |
| `email_upgraded` | 1 | `alt.nikhil.chopra70@...` → `nikhil.chopra70@...` |
| `duplicate_header` | 1 | Source3 row 16 — header repeated mid-file |
| `blank_row` | 1 | Source2 row 12 — completely empty |
| `ambiguous_duplicate` | 1 | Two Arjun Mehtas with different phones in source3 |
| `alternate_email` | 1 | `alt.` prefix email variant |
| `abbreviated_name` | 1 | `R. Verma` short form |

### Detailed Issues by Source

#### Source 1 — `source1_naukri_applicants.csv` (169 issues)

| # | Issue | Example | Fix |
|---|-------|---------|-----|
| 1 | **Phone format variants** (5+) | `+919000000254`, `09000000287`, `9000000237` | Stripped to last 10 digits |
| 2 | **Date format variants** (5) | `24-07-2026`, `2026-08-08`, `07/13/2026`, `7 Jul 2026` | Parsed to ISO `YYYY-MM-DD` |
| 3 | **CTC in mixed units** | `417964` (rupees) vs `4.2` (lakhs) | Values ≤100 → lakhs; >100 → rupees÷100000 |
| 4 | **City casing/aliasing** | `pune`, `GURGAON`, `gurugram`, `new delhi` | Alias map + title case |
| 5 | **Duplicate: R. Verma / Rohit Verma** | Rows 25 & 31 — same email+phone | Merged, name upgraded to `Rohit Verma` |
| 6 | **Duplicate: Nikhil Chopra** | Rows 27 (`alt.` email) & 37 — same phone | Merged, email upgraded to non-alt |
| 7 | **Abbreviated name** | `R. Verma` in row 25 | Detected and upgraded on merge |
| 8 | **Trailing whitespace** | `Noida `, `gurugram ` | Stripped |
| 9 | **Skills mixed casing** | `LangChain`, `REST APIs` | Lowercased, sorted, deduped |

#### Source 2 — `source2_gig_workers.csv` (110 issues)

| # | Issue | Example | Fix |
|---|-------|---------|-----|
| 10 | **Shifted/corrupted row** | Row 20: skills in email column | Detected by heuristic, skipped |
| 11 | **Blank row** | Row 12: all fields empty | Skipped |
| 12 | **Email ALL-CAPS** | `ISHA.CHOPRA95@MAILTEST.EXAMPLE.ORG` | Lowercased |
| 13 | **Mixed rate formats** | `1415/hr`, `15k/month`, `72k/month` | Stored as-is, logged as mixed |
| 14 | **Status casing** | `Active`, `active`, `ACTIVE`, `paused` | Lowercased |
| 15 | **Two Deepak Nairs** | Different emails, different cities | Kept separate (different people) |
| 16 | **Arjun Mehta email mismatch** | `arjun.mehta77@...` (source2) vs `arjun.mehta9@...` (source1) | Matched via source3 phone |

#### Source 3 — `source3_cbnexus_contacts.csv` (69 issues)

| # | Issue | Example | Fix |
|---|-------|---------|-----|
| 17 | **Duplicate header row** | Row 16 repeats `Name,Phone Number,...` | Skipped |
| 18 | **Verified inconsistency** | `Y`, `yes`, `Yes`, `No`, `N` | Mapped to 1/0 |
| 19 | **Name ALL-CAPS** | `RITU SHARMA`, `MEERA BHATIA` | Title-cased |
| 20 | **Two Arjun Mehtas** | Rows 5 & 28 — different phone numbers | Kept both; row 5 matched source1 by phone |
| 21 | **Phone format variants** | `919000000231`, `+91-9000000131` | Stripped to last 10 digits |

#### Cross-Source Conflicts (6 issues)

| Person | Source A City | Source B City | Resolution |
|--------|-------------|-------------|------------|
| Priya Singh | Gurugram (source1) | Gurugram (source3) | Consistent after alias |
| Arjun Mishra | Delhi (source1) | New Delhi (source3) | Kept first seen |
| Meera Bhatia | Delhi NCR (source1) | Delhi (source3) | Kept first seen |
| Rahul Malhotra | New Delhi (source1) | Delhi NCR (source3) | Kept first seen |
| Priya Saxena | Delhi (source1) | New Delhi (source3) | Kept first seen |
| Arjun Mishra | Delhi (source1) | New Delhi (source3) | Kept first seen |

> [!NOTE]
> All 348 issues are stored in the `data_issues` table in `consultbae.db` with full details: source file, row number, field, issue type, original value, fixed value, and description.

---

## All Project Files

| File | Lines | Purpose |
|------|-------|---------|
| [merge_sources.py](file:///c:/Users/aayus/Desktop/consultbae%20claude/merge_sources.py) | ~890 | Task 1: CSV merge pipeline |
| [app.py](file:///c:/Users/aayus/Desktop/consultbae%20claude/app.py) | ~185 | Task 3: Flask web server |
| [audio_analyzer.py](file:///c:/Users/aayus/Desktop/consultbae%20claude/audio_analyzer.py) | ~240 | Task 3: Audio property extraction |
| [templates/index.html](file:///c:/Users/aayus/Desktop/consultbae%20claude/templates/index.html) | ~700 | Task 3: Frontend (HTML/CSS/JS) |
| [consultbae.db](file:///c:/Users/aayus/Desktop/consultbae%20claude/consultbae.db) | — | SQLite database (3 tables) |
| [check_db.py](file:///c:/Users/aayus/Desktop/consultbae%20claude/check_db.py) | ~35 | Verification helper |

### Quick Start
```bash
# Step 1: Run merge pipeline
python merge_sources.py

# Step 2: Start audio app
python app.py
# Open http://127.0.0.1:5000
```
## Stuck Log

**1. Audio Feature Extraction Without FFmpeg**
*   **The Problem:** I needed to extract duration, bitrate, loudness, and a noise estimate from audio files, but standard libraries like `pydub` or `librosa` require heavy external dependencies (like FFmpeg) which complicates deployment.
*   **The AI Prompt:** "How to extract audio duration, sample rate, loudness in dBFS, and estimate noise in Python using only the standard library or lightweight packages without FFmpeg?"
*   **The Solution:** I utilized Python's built-in `wave` module to read raw frames and `numpy` to calculate the Root Mean Square (RMS) for dBFS loudness. For noise estimation, I implemented a spectral flatness algorithm (geometric mean divided by arithmetic mean of the power spectrum). 
*   **Rejected Suggestion:** AI suggested using `librosa.feature.spectral_flatness`. I rejected this because `librosa` is a massive dependency that significantly slows down deployment and often causes version conflicts in lightweight web apps.

**2. Cross-Source Deduplication Without Unique IDs**
*   **The Problem:** The three CSV files contained overlapping candidates but no universal ID, meaning standard SQL `JOIN` or Pandas `merge` operations would fail or create duplicates.
*   **The AI Prompt:** "Write a Python deduplication logic for 3 CSV files where people might share an email, a phone number, or just a name and city, ensuring the richest data is kept."
*   **The Solution:** I built a 3-tier fallback strategy using dictionary indexing. The script checks for email matches first, falls back to phone numbers, and finally uses a normalized "name + city" string. I added custom heuristic checks to upgrade abbreviated names (e.g., `R. Verma` to `Rohit Verma`) and prefer non-alt emails. 
*   **Rejected Suggestion:** AI suggested a Pandas `outer merge` with `fillna()`. I rejected this because it is too rigid; it cannot intelligently handle transitive matching (e.g., Source A matches Source B by email, and Source B matches Source C by phone).

---

## Task 5 — App Scaling & Bottleneck Analysis

Launching this audio collection app to 5,000 gig workers over a single weekend requires shifting from a local Flask/SQLite architecture to a production-ready cloud environment[cite: 2, 5].

### Architecture Bottlenecks
*   **Storage Constraints:** 5,000 workers submitting 5MB audio files equals 25GB of data. Storing these locally in an `uploads/` directory will quickly max out standard server disk space and cause the app to crash.
*   **System Failures:** The current architecture processes audio synchronously[cite: 5]. If 500 workers submit audio simultaneously, the CPU-heavy `numpy` FFT calculations will block the Flask server, causing gateway timeouts.
*   **Database Locks:** SQLite handles concurrent reads well but locks the entire database during writes. 5,000 weekend writes will lead to `database is locked` errors.

### Required Infrastructure Upgrades
*   **Upload Handling:** I would implement pre-signed URLs to upload audio files directly from the browser to an AWS S3 bucket. This bypasses the Flask server entirely, preventing bandwidth bottlenecks.
*   **Asynchronous Processing:** I would move the `audio_analyzer.py` logic into a background worker queue (using Celery + Redis). The web app would instantly return a "Success" message to the gig worker, while the server processes the spectral flatness and dBFS calculations in the background. 
*   **Duplicates & Cost:** To prevent workers from spamming submissions, I would implement frontend button-disabling upon click, and backend rate-limiting per phone number. For cost, utilizing S3 for storage and serverless functions (like AWS Lambda) for the audio processing ensures we only pay for the exact compute time used during the weekend spike.
