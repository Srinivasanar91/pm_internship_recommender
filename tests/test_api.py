import os
import pytest
from app import app as flask_app, db, User, Internship
import engine

@pytest.fixture
def client():
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    flask_app.config['TESTING'] = True

    with flask_app.app_context():
        db.create_all()
        # minimal seed
        u = User(name="ApiUser", qualification="Graduation", skills="C, Python", languages="English", current_address="Coimbatore", category="OBC")
        db.session.add(u)
        i = Internship(company_name="X", title="Software Intern", required_qualification="Graduation", required_skills="C, Python", required_languages="English", location="Coimbatore", preferred_category="OBC", is_pwd_friendly=1, sector="IT")
        db.session.add(i)
        db.session.commit()

        engine.init_engine(flask_app, db, User, Internship, None)

        client = flask_app.test_client()
        yield client

        db.session.remove()
        db.drop_all()

def test_recommend_endpoint_get(client):
    rv = client.get("/recommend/1?n=3&min_score=0")
    assert rv.status_code == 200
    data = rv.get_json()
    assert isinstance(data, list)
    assert len(data) >= 0

def test_admin_rebuild_and_status(client):
    # set ADMIN_TOKEN in env for protection usage in test paths (we call route directly)
    token = "testtoken"
    os.environ['ADMIN_TOKEN'] = token
    # rebuild tfidf
    rv = client.get(f"/admin/rebuild_tfidf?token={token}")
    assert rv.status_code in (200, 201)
    # status
    rv2 = client.get(f"/admin/tfidf_status?token={token}")
    assert rv2.status_code == 200
    j = rv2.get_json()
    assert 'loaded' in j and 'n_internships' in j
