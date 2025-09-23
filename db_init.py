# db_init.py
import sqlite3
from datetime import datetime

DB = "internship_portal.db"

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Users table (minimal rich profile)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        gender TEXT,
        dob TEXT,
        father_name TEXT,
        mother_name TEXT,
        category TEXT,
        pwd INTEGER DEFAULT 0,
        address_permanent TEXT,
        address_current TEXT,
        mobile TEXT,
        email TEXT,
        qualification TEXT,
        course TEXT,
        university TEXT,
        year_of_passing INTEGER,
        grade TEXT,
        skills TEXT,        -- comma separated
        languages TEXT,     -- comma separated
        interests TEXT,     -- comma separated (domains)
        experience TEXT,
        certifications TEXT,
        hobbies TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Internships table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS internships (
        internship_id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        company_name TEXT,
        location TEXT,
        required_qualification TEXT,
        required_skills TEXT,     -- comma separated
        required_languages TEXT,  -- comma separated
        sector TEXT,
        category_preference TEXT, -- e.g., 'SC/ST/OBC/All'
        pwd_friendly INTEGER DEFAULT 1,
        description TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Recommendations log (optional)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS recommendations (
        rec_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        internship_id INTEGER,
        score REAL,
        reason TEXT,
        recommended_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()
    print("DB and tables created (or verified).")

def insert_sample_data():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Sample user (Arjun)
    cur.execute("""
    INSERT INTO users
    (name, gender, dob, father_name, mother_name, category, pwd, address_permanent, address_current,
     mobile, email, qualification, course, university, year_of_passing, grade,
     skills, languages, interests, experience, certifications, hobbies)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "Arjun Kumar", "Male", "2001-05-12", "R. Kumar", "S. Meena", "OBC", 0,
        "Village A, Coimbatore, Tamil Nadu", "Hostel, Coimbatore",
        "9876543210", "arjun@example.com", "Graduation", "B.Sc Computer Science",
        "Bharathiar University", 2022, "7.8 CGPA",
        "C, Python", "Tamil, English", "IT", "None", "NPTEL - Data Structures", "Coding, Chess"
    ))

    # Another sample user (Meena)
    cur.execute("""
    INSERT INTO users
    (name, gender, dob, father_name, mother_name, category, pwd, address_permanent, address_current,
     mobile, email, qualification, course, university, year_of_passing, grade,
     skills, languages, interests, experience, certifications, hobbies)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "Meena Sharma", "Female", "2000-08-20", "R. Sharma", "L. Sharma", "General", 0,
        "Jaipur, Rajasthan", "Jaipur",
        "9123456780", "meena@example.com", "Graduation", "B.A. English Literature",
        "University of Rajasthan", 2021, "68%",
        "Content Writing, SEO", "Hindi, English", "Marketing", "None", "Google Digital", "Reading, Music"
    ))

    # Sample internships
    internships = [
        ("Software Developer Intern", "TechSoft Pvt Ltd", "Coimbatore", "Graduation", "C, Python", "English, Tamil", "IT", "All", 1, "Work on mobile-first React apps and small backend tasks."),
        ("Data Entry & QA Assistant", "City Gov", "Coimbatore", "12th", "Excel, Data Entry", "English, Tamil", "Government Services", "All", 1, "Digitize records and verify forms."),
        ("NGO Digital Support Intern", "Rural Connect NGO", "Madurai", "12th", "Basic IT, Tamil, Excel", "Tamil, English", "NGO", "SC/ST/OBC", 1, "Help digitize NGO data and run local campaigns."),
        ("Marketing Intern", "Bright Media", "Jaipur", "Graduation", "SEO, Content Writing", "Hindi, English", "Marketing", "All", 0, "Assist with local digital campaigns.")
    ]
    cur.executemany("""
    INSERT INTO internships
    (title, company_name, location, required_qualification, required_skills, required_languages, sector, category_preference, pwd_friendly, description)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, internships)

    conn.commit()
    conn.close()
    print("Inserted sample users and internships.")

if __name__ == "__main__":
    init_db()
    insert_sample_data()
    print("Database initialized with sample data.")

