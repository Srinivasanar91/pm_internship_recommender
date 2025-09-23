# engine.py
"""
Hybrid recommender with TF-IDF caching + persistence, non-circular init.

Exports:
 - init_engine(app, db, User, Internship, Application=None)
 - recommend_for_user_id(user_id, top_n=5, min_score=40, debug=False)
 - rebuild_tfidf(max_features=1000)  # admin callable
 - tfidf_status()
"""

import re
from collections import defaultdict
from math import isfinite
import threading
import os
import joblib
from scipy.sparse import save_npz, load_npz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.exceptions import NotFittedError
from datetime import datetime

# -------------------------
# Tunable weights (rule-based)
# -------------------------
WEIGHTS = {
    "qualification": 30.0,
    "skills": 30.0,
    "location": 15.0,
    "languages": 7.0,
    "inclusiveness": 4.0,
    "interests": 8.0,
    "sector": 6.0
}

# How to combine rule & tfidf (you had RULE_WEIGHT/TFIDF_WEIGHT earlier)
RULE_WEIGHT = 0.80
TFIDF_WEIGHT = 0.20

# -------------------------
# TF-IDF cache (module-level)
# -------------------------
_tfidf_cache = {
    "vectorizer": None,
    "intern_vectors": None,   # sparse matrix
    "intern_ids": [],         # parallel list of internship ids
    "intern_corpus": []       # raw corpus list
}
_cache_lock = threading.Lock()

# TF-IDF config (defaults)
TFIDF_CONFIG = {
    "max_features": int(os.environ.get("TFIDF_MAX_FEATURES", 1000)),
    "ngram_range": (1, 2),
    "stop_words": "english"
}

# Persistence files
TFIDF_DIR = os.environ.get("TFIDF_DIR", ".cache")
VECT_FILE = os.path.join(TFIDF_DIR, "tfidf_vectorizer.joblib")
MAT_FILE = os.path.join(TFIDF_DIR, "tfidf_matrix.npz")
IDX_FILE  = os.path.join(TFIDF_DIR, "internship_index.joblib")

# -------------------------
# DB references (filled by init_engine)
# -------------------------
db = None
User = None
Internship = None
Application = None
flask_app = None

# -------------------------
# Helpers
# -------------------------
def _to_set(text):
    if not text:
        return set()
    if isinstance(text, (list, set)):
        items = text
    else:
        items = re.split(r'[,;]', str(text))
    return set([s.strip().lower() for s in items if s and s.strip()])

def _normalize_text(text):
    return (text or "").strip().lower()

def ensure_cache_dir():
    if not os.path.exists(TFIDF_DIR):
        os.makedirs(TFIDF_DIR, exist_ok=True)

# -------------------------
# Rule-based scoring (unchanged)
# -------------------------
def calculate_rule_score(user, internship):
    bd = defaultdict(lambda: 0.0)
    # Qualification
    user_qual = _normalize_text(getattr(user, "qualification", "") or "")
    req_qual = _normalize_text(getattr(internship, "required_qualification", "") or "")
    bd["qualification"] = WEIGHTS["qualification"] if (user_qual and req_qual and user_qual in req_qual) else 0.0

    # Skills overlap
    user_skills = _to_set(getattr(user, "skills", "") or "")
    req_skills = _to_set(getattr(internship, "required_skills", "") or "")
    if req_skills:
        matched = user_skills & req_skills
        ratio = len(matched) / len(req_skills)
        bd["skills"] = round(WEIGHTS["skills"] * ratio, 4)
        bd["matched_skills"] = sorted(list(matched))
    else:
        bd["skills"] = 0.0
        bd["matched_skills"] = []

    # Location
    user_addr = _normalize_text(getattr(user, "current_address", "") or "")
    internship_loc = _normalize_text(getattr(internship, "location", "") or "")
    bd["location"] = WEIGHTS["location"] if (internship_loc and user_addr and internship_loc in user_addr) else 0.0

    # Languages
    user_langs = _to_set(getattr(user, "languages", "") or "")
    req_langs = _to_set(getattr(internship, "required_languages", "") or "")
    matched_langs = sorted(list(user_langs & req_langs))
    bd["languages"] = WEIGHTS["languages"] if matched_langs else 0.0
    bd["matched_languages"] = matched_langs

    # Inclusiveness (category + pwd)
    bd["inclusiveness"] = 0.0
    try:
        pref_cat = _normalize_text(getattr(internship, "preferred_category", "") or "")
        user_cat = _normalize_text(getattr(user, "category", "") or "")
        if pref_cat and user_cat and pref_cat == user_cat:
            bd["inclusiveness"] += WEIGHTS["inclusiveness"] * 0.6
        if getattr(internship, "is_pwd_friendly", 0) == 1 and getattr(user, "pwd", 0) == 1:
            bd["inclusiveness"] += WEIGHTS["inclusiveness"] * 0.4
    except Exception:
        bd["inclusiveness"] += 0.0

    # Interests
    user_interests = _to_set(getattr(user, "interests", "") or "")
    if not user_interests:
        user_interests |= _to_set(getattr(user, "course", "") or "")
        user_interests |= _to_set(getattr(user, "hobbies", "") or "")
    internship_sector = _to_set(getattr(internship, "sector", "") or "")
    title_kw = _to_set(getattr(internship, "title", "") or "")
    interests_matched = sorted(list(user_interests & (internship_sector | title_kw)))
    if user_interests:
        ratio = len(interests_matched) / max(1, len(user_interests))
        bd["interests"] = round(WEIGHTS["interests"] * ratio, 4)
    else:
        bd["interests"] = 0.0
    bd["matched_interests"] = interests_matched

    # Sector bonus
    bd["sector"] = WEIGHTS["sector"] if (internship_sector and user_interests and (internship_sector & user_interests)) else 0.0

    # rule total
    total_rule = 0.0
    for k in ("qualification", "skills", "location", "languages", "inclusiveness", "interests", "sector"):
        total_rule += float(bd.get(k, 0.0))
    bd["rule_total"] = round(total_rule, 4)
    return bd

# -------------------------
# TF-IDF corpus helpers & caching (unchanged)
# -------------------------
def _build_internship_corpus(internships):
    corpus = []
    ids = []
    for i in internships:
        parts = []
        for attr in ("title", "sector", "required_skills", "required_languages", "company_name"):
            v = getattr(i, attr, None)
            if v:
                parts.append(str(v))
        corpus.append(" ".join(parts))
        ids.append(getattr(i, "id", None) or getattr(i, "internship_id", None))
    return corpus, ids

def _build_user_text(user):
    parts = []
    for attr in ("skills", "interests", "course", "hobbies", "languages", "qualification"):
        v = getattr(user, attr, None)
        if v:
            parts.append(str(v))
    return " ".join(parts)

def build_tfidf_cache(internships):
    """
    Builds or refreshes the TF-IDF cache. Call this at startup and whenever internships change.
    This function uses TFIDF_CONFIG settings.
    """
    global _tfidf_cache
    corpus, ids = _build_internship_corpus(internships)
    if not corpus or all(not c.strip() for c in corpus):
        with _cache_lock:
            _tfidf_cache["vectorizer"] = None
            _tfidf_cache["intern_vectors"] = None
            _tfidf_cache["intern_ids"] = []
            _tfidf_cache["intern_corpus"] = []
        return {"built": False, "reason": "no_corpus"}

    vectorizer = TfidfVectorizer(max_features=TFIDF_CONFIG["max_features"],
                                 ngram_range=TFIDF_CONFIG["ngram_range"],
                                 stop_words=TFIDF_CONFIG["stop_words"])
    vecs = vectorizer.fit_transform(corpus)
    with _cache_lock:
        _tfidf_cache["vectorizer"] = vectorizer
        _tfidf_cache["intern_vectors"] = vecs
        _tfidf_cache["intern_ids"] = ids
        _tfidf_cache["intern_corpus"] = corpus

    return {"built": True, "n_internships": len(ids), "n_features": vecs.shape[1]}

def _compute_tfidf_scores_from_cache(user_text):
    """
    Compute similarity between user_text and cached internship vectors.
    Returns dict mapping internship_id -> similarity (0..1).
    """
    with _cache_lock:
        vectorizer = _tfidf_cache.get("vectorizer")
        intern_vectors = _tfidf_cache.get("intern_vectors")
        ids = _tfidf_cache.get("intern_ids", [])

    if not vectorizer or intern_vectors is None:
        return {}

    try:
        user_vec = vectorizer.transform([user_text])
        sims = cosine_similarity(user_vec, intern_vectors)[0]
    except Exception:
        return {}
    out = {}
    for idx, iid in enumerate(ids):
        sim = float(sims[idx]) if isfinite(sims[idx]) else 0.0
        out[iid] = sim
    return out

# -------------------------
# Persistence: save & load TF-IDF cache
# -------------------------
def save_tfidf_cache():
    """
    Save current in-memory tfidf cache to disk (vectorizer, matrix, index).
    Safe to call after build_tfidf_cache.
    """
    ensure_cache_dir()
    with _cache_lock:
        vect = _tfidf_cache.get("vectorizer")
        mat = _tfidf_cache.get("intern_vectors")
        ids = _tfidf_cache.get("intern_ids", [])
        corpus = _tfidf_cache.get("intern_corpus", [])

    if vect is None or mat is None:
        return {"saved": False, "reason": "empty_cache"}
    try:
        joblib.dump(vect, VECT_FILE)
        save_npz(MAT_FILE, mat)
        joblib.dump(ids, IDX_FILE)
        # optionally save corpus also
        joblib.dump(corpus, os.path.join(TFIDF_DIR, "intern_corpus.joblib"))
        return {"saved": True}
    except Exception as e:
        if flask_app:
            flask_app.logger.exception("Failed to save TFIDF cache: %s", e)
        return {"saved": False, "reason": str(e)}

def load_tfidf_cache():
    """
    Load tfidf cache from disk into memory. Returns True if loaded.
    """
    if not (os.path.exists(VECT_FILE) and os.path.exists(MAT_FILE) and os.path.exists(IDX_FILE)):
        return False
    try:
        vect = joblib.load(VECT_FILE)
        mat = load_npz(MAT_FILE)
        ids = joblib.load(IDX_FILE)
        corpus = joblib.load(os.path.join(TFIDF_DIR, "intern_corpus.joblib"))
        with _cache_lock:
            _tfidf_cache["vectorizer"] = vect
            _tfidf_cache["intern_vectors"] = mat
            _tfidf_cache["intern_ids"] = ids
            _tfidf_cache["intern_corpus"] = corpus
        return True
    except Exception as e:
        if flask_app:
            flask_app.logger.exception("Failed to load TFIDF cache: %s", e)
        return False

def tfidf_status():
    with _cache_lock:
        vect = _tfidf_cache.get("vectorizer")
        mat = _tfidf_cache.get("intern_vectors")
        ids = _tfidf_cache.get("intern_ids", [])
    return {
        "loaded": vect is not None and mat is not None,
        "n_internships": len(ids),
        "n_features": mat.shape[1] if mat is not None else 0,
        "vect_path": VECT_FILE,
        "mat_path": MAT_FILE,
        "last_checked": datetime.utcnow().isoformat() + "Z"
    }

# -------------------------
# Combined scoring and recommendation (unchanged logic, but wrapped)
# -------------------------
def recommend_internships_for_user(user, internships, top_n=5, min_score=40):
    # 1) rule-based breakdowns
    recs_rule = {}
    for internship in internships:
        iid = getattr(internship, "id", None) or getattr(internship, "internship_id", None)
        bd = calculate_rule_score(user, internship)
        recs_rule[iid] = bd

    # 2) TF-IDF scores from cache (fallback to zeros if not available)
    user_text = _build_user_text(user)
    tfidf_scores = _compute_tfidf_scores_from_cache(user_text)
    if not tfidf_scores:
        # fallback: all zeros (we keep rule-based only, safe)
        tfidf_scores = {iid: 0.0 for iid in recs_rule.keys()}

    # 3) combine
    results = []
    for internship in internships:
        iid = getattr(internship, "id", None) or getattr(internship, "internship_id", None)
        bd = recs_rule.get(iid, {})
        rule_total = float(bd.get("rule_total", 0.0))
        rule_total = max(0.0, min(rule_total, 100.0))

        tfidf_sim = float(tfidf_scores.get(iid, 0.0) or 0.0)
        tfidf_score = tfidf_sim * 100.0

        final = RULE_WEIGHT * rule_total + TFIDF_WEIGHT * tfidf_score
        final = round(final, 4)

        result = {
            "internship_id": iid,
            "company_name": getattr(internship, "company_name", None),
            "title": getattr(internship, "title", None),
            "location": getattr(internship, "location", None),
            "required_skills": getattr(internship, "required_skills", None),
            "required_languages": getattr(internship, "required_languages", None),
            "sector": getattr(internship, "sector", None),
            "score": final,
            "score_breakdown": {
                "rule_score": rule_total,
                "tfidf_sim": round(tfidf_sim, 4),
                "tfidf_score": round(tfidf_score, 4),
                "final_score": final,
                "rule_detail": {
                    "qualification": bd.get("qualification", 0.0),
                    "skills": bd.get("skills", 0.0),
                    "location": bd.get("location", 0.0),
                    "languages": bd.get("languages", 0.0),
                    "inclusiveness": round(bd.get("inclusiveness", 0.0), 4),
                    "interests": bd.get("interests", 0.0),
                    "sector": bd.get("sector", 0.0),
                    "matched_skills": bd.get("matched_skills", []),
                    "matched_languages": bd.get("matched_languages", []),
                    "matched_interests": bd.get("matched_interests", []),
                }
            }
        }

        if result["score"] >= min_score:
            results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]

# -------------------------
# Engine bootstrap / integration helpers (avoid circular imports)
# -------------------------
def init_engine(app_obj, db_obj, User_model, Internship_model, Application_model=None):
    """
    Initialize engine references and attempt to load persisted TF-IDF cache.
    Call this from app.py AFTER models and db are defined.
    """
    global db, User, Internship, Application, flask_app
    db = db_obj
    User = User_model
    Internship = Internship_model
    Application = Application_model
    flask_app = app_obj

    # try load cache from disk
    ok = load_tfidf_cache()
    if flask_app:
        if ok:
            flask_app.logger.info("engine.init_engine: loaded TF-IDF cache (%d internships, %d features)",
                                  len(_tfidf_cache.get("intern_ids", [])),
                                  _tfidf_cache.get("intern_vectors").shape[1] if _tfidf_cache.get("intern_vectors") is not None else 0)
        else:
            flask_app.logger.info("engine.init_engine: no TF-IDF cache on disk (call rebuild_tfidf)")

def rebuild_tfidf(max_features=None):
    """
    Rebuild TF-IDF cache from current internships in DB and persist to disk.
    Returns dict with build result.
    """
    if db is None or Internship is None:
        return {"built": False, "reason": "engine_not_initialized"}
    try:
        internships = db.session.query(Internship).all()
    except Exception:
        try:
            rows = db.session.execute("SELECT id, title, required_skills, required_languages, location, sector FROM internship").fetchall()
            internships = []
            for r in rows:
                # create a simple object-like dict to pass into build_tfidf_cache logic
                internships.append(type("X", (), {"id": r[0], "title": r[1] or "", "required_skills": r[2] or "", "required_languages": r[3] or "", "location": r[4] or "", "sector": r[5] or ""})())
        except Exception:
            internships = []

    if max_features:
        TFIDF_CONFIG["max_features"] = int(max_features)
    res = build_tfidf_cache(internships)
    # persist when build succeeded
    if res.get("built"):
        save_res = save_tfidf_cache()
        res["saved"] = save_res.get("saved", False)
    return res

def recommend_for_user_id(user_id, top_n=5, min_score=40, debug=False):
    """
    Convenience wrapper: fetch user & internships from DB and call recommend_internships_for_user.
    """
    if db is None or User is None or Internship is None:
        raise RuntimeError("Engine not initialized. Call init_engine(app, db, User, Internship, Application) first.")
    user = db.session.query(User).get(user_id)
    if not user:
        return []
    internships = db.session.query(Internship).all()
    return recommend_internships_for_user(user, internships, top_n=top_n, min_score=min_score)
