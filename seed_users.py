from models import SessionLocal, User

session = SessionLocal()

user1 = User(
    name="Arun Kumar",
    skills="Python, SQL, C"
)

user2 = User(
    name="Priya Sharma",
    skills="Finance, Accounting, Excel"
)

session.add_all([user1, user2])
session.commit()
session.close()

print("✅ Users seeded successfully!")
