from app import app, db, Internship
from engine import build_tfidf_cache, _tfidf_cache
from sqlalchemy import inspect

with app.app_context():
    internships = Internship.query.all()
    print("Found", len(internships), "internships in DB. Building TF-IDF cache...")
    try:
        build_tfidf_cache(internships)
        # report cache contents
        cached_ids = _tfidf_cache.get("intern_ids") or []
        corpus = _tfidf_cache.get("intern_corpus") or []
        print("TF-IDF cache built. Cached internships:", len(cached_ids))
        # show first 5 ids for sanity
        print("Sample cached ids:", cached_ids[:5])
        print("Sample corpus entries (first 3):")
        for c in corpus[:3]:
            print(" -", (c[:140] + "...") if len(c) > 140 else c)
    except Exception as e:
        print("Cache rebuild failed:", e)
