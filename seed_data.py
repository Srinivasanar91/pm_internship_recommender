from app import db, User, Internship, app

with app.app_context():
    # Reset database
    db.drop_all()
    db.create_all()

    # ---- Users ----
    users = [
        User(
            name="Srinivasan",
            gender="Male",
            dob="1990-05-10",
            father_name="Arul",
            mother_name="Meena",
            category="OBC",
            pwd=0,
            permanent_address="Pudukkottai",
            current_address="Coimbatore",
            mobile="9876543210",
            email="srinivasan@example.com",
            qualification="Graduation",
            course="B.Sc Computer Science",
            specialization="Computer Science",
            university="H.H The Rajah’s College",
            year_of_passing=2014,
            cgpa=7.8,
            skills="C, Python, SQL",
            languages="Tamil, English",
            past_experience="Teaching Assistant",
            certifications="Python Certification",
            hobbies="Reading, Coding"
        ),
        User(
            name="Priya",
            gender="Female",
            dob="1995-07-12",
            father_name="Ravi",
            mother_name="Lakshmi",
            category="SC",
            pwd=1,
            permanent_address="Madurai",
            current_address="Chennai",
            mobile="9876501234",
            email="priya@example.com",
            qualification="Diploma",
            course="Diploma in IT",
            specialization="Information Technology",
            university="Govt Polytechnic",
            year_of_passing=2015,
            cgpa=8.2,
            skills="Java, HTML, CSS",
            languages="English, Tamil",
            past_experience="Web Developer Intern",
            certifications="Java Certification",
            hobbies="Painting"
        )
    ]

    # ---- Internships ----
    internships = [
        Internship(
            company_name="XYZ Corp",
            title="Software Intern",
            required_qualification="Graduation",
            required_skills="C, Python",
            required_languages="English",
            location="Coimbatore",
            preferred_category="OBC",
            is_pwd_friendly=1
        ),
        Internship(
            company_name="ABC Tech",
            title="Web Developer Intern",
            required_qualification="Diploma",
            required_skills="Java, HTML, CSS",
            required_languages="English, Tamil",
            location="Chennai",
            preferred_category="SC",
            is_pwd_friendly=1
        ),
        Internship(
            company_name="DataWorks",
            title="Data Analyst Intern",
            required_qualification="Graduation",
            required_skills="SQL, Python",
            required_languages="English",
            location="Bangalore",
            preferred_category="General",
            is_pwd_friendly=0
        )
        
    ]

    # Insert all
    db.session.add_all(users + internships)
    db.session.commit()

    print("✅ Database seeded with sample users & internships.")
