import sqlite3
import requests
import time

WEBHOOK_URL = "https://hook.eu1.make.com/id41b4dhbsd474b4ayqradp14n5xclza"

# Connect to database
conn = sqlite3.connect('consultbae.db')
cursor = conn.cursor()

# Ensure skill_category column exists in the persons table
try:
    cursor.execute("ALTER TABLE persons ADD COLUMN skill_category TEXT;")
    conn.commit()
except sqlite3.OperationalError:
    pass # Column already exists

# Fetch persons that have not been tagged yet
cursor.execute("SELECT id, full_name, email, skills FROM persons WHERE skills IS NOT NULL AND (skill_category IS NULL OR skill_category = '')")
rows = cursor.fetchall()

print(f"Tagging {len(rows)} remaining candidates via Make.com LLM flow...")

for person_id, full_name, email, skills in rows:
    payload = {"name": full_name, "email": email, "skills": skills}
    try:
        res = requests.post(WEBHOOK_URL, json=payload, timeout=45)
        
        if res.status_code == 200:
            try:
                data = res.json()
                category = data.get("assigned_category", "Uncategorized").strip()
                cursor.execute("UPDATE persons SET skill_category = ? WHERE id = ?", (category, person_id))
                conn.commit()
                print(f"✅ Tagged {full_name} -> {category}")
            except Exception:
                print(f"⚠️ {full_name}: Received non-JSON response: {res.text[:60]}")
        else:
            print(f"❌ Failed for {full_name}: Status {res.status_code} - {res.text[:60]}")
            
    except Exception as e:
        print(f"⚠️ Error for {full_name}: {e}")
        
    time.sleep(3.5) # 2s pause to stay within Gemini API free rate limits (15 RPM)

conn.close()
print("\nDone! Database successfully updated.")