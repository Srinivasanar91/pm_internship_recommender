from app import db, app
from sqlalchemy import inspect
with app.app_context():
    insp = inspect(db.engine)
    # adjust table name: SQLAlchemy default is the lowercase class name -> "user" or "users"
    tables = insp.get_table_names()
    print("Tables in DB:", tables)
    # try both likely names
    for t in ("user", "users"):
        if t in tables:
            cols = [c["name"] for c in insp.get_columns(t)]
            print(f"Columns in table \"{t}\":", cols)
