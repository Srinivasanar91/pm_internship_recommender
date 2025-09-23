import os
import tempfile
import pytest

from app import app as flask_app, db, User, Internship
import engine

@pytest.fixture
def client():
    # Use an in-memory SQLite DB for tests
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    flask_app.config['TESTING'] = True

    with flask_app.app_context():
        db.create_all()
        # Seed a couple of users + internships
        u1 = User(
            name="Test User",
            gender="Male",
            dob="2000-01-01",
            father_name="F",
            mother_name="M",
            category="OBC",
            pwd=0,
            permanent_address="Village",
            current_address="Coimbatore",
            mobile="12345",
            email="t@example.com",
            qualification="Graduation",
            course="B.Sc Computer Science",
            specialization="CS",
            university="Test Univ",
            year_of_passing=2022,
            cgpa=7.5,
            skills="C, Python",
            languages="English, Tamil",
            past_experience="None",
            certifications="None",
            hobbies="Coding",
        )
        u2 = User(
            name="Other",
            qualification="Diploma",
            skills="Java, HTML",
            languages="English",
            current_address="Chennai",
            category="SC",
            pwd=1
        )
        db.session.add_all([u1, u2])
        db.session.commit()

        i1 = Internship(
            company_name="X Corp",
            title="Software Intern",
            required_qualification="Graduation",
            required_skills="C, Python",
            required_languages="English",
            location="Coimbatore",
            preferred_category="OBC",
            is_pwd_friendly=1,
            sector="IT"
        )
        i2 = Internship(
            company_name="Data Co",
            title="Data Assistant",
            required_qualification="Graduation",
            required_skills="SQL, Python",
            required_languages="English",
            location="Bangalore",
            preferred_category="General",
            is_pwd_friendly=0,
            sector="Data"
        )
        db.session.add_all([i1, i2])
        db.session.commit()

        # init engine with app's models
        engine.init_engine(flask_app, db, User, Internship, None)

        yield flask_app.test_client()

        db.session.remove()
        db.drop_all()

def test_build_and_persist_tfidf_cache(client, tmp_path):
    # ensure TFIDF_DIR is an isolated tmp directory for the test
    os.environ['TFIDF_DIR'] = str(tmp_path / "tfidf_test_cache")
    # rebuild from DB
    res = engine.rebuild_tfidf(max_features=500)
    assert 'built' in res
    # if built, persisted files should exist
    if res.get("built"):
        assert (tmp_path / "tfidf_test_cache" / "tfidf_vectorizer.joblib").exists()
        assert (tmp_path / "tfidf_test_cache" / "tfidf_matrix.npz").exists()

def test_recommendation_scores(client):
    # check recommendations for user id 1
    recs = engine.recommend_for_user_id(1, top_n=5, min_score=0)
    assert isinstance(recs, list)
    # we expect at least one recommendation exists (rule-based + tfidf optional)
    assert any(r['title'] == 'Software Intern' or r['company_name'] == 'X Corp' for r in recs)
    # ensure score_breakdown keys exist
    for r in recs:
        assert 'score' in r
        assert 'score_breakdown' in r
