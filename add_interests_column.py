from app import db, app
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text("ALTER TABLE user ADD COLUMN interests TEXT;"))
        db.session.commit()
        print("✅ Added 'interests' column to User table.")
    except Exception as e:
        print("⚠️ Error (maybe column already exists):", e)