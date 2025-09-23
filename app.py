# app.py
import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from engine import build_tfidf_cache, recommend_internships_for_user
import threading


# Import engine function (ensure engine.py exports this)
from engine import recommend_internships_for_user

# ----------------------
# App + DB config
# ----------------------
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///recommender.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config["ADMIN_TOKEN"] = os.environ.get("ADMIN_TOKEN", "dev-token-change-this")

db = SQLAlchemy(app)

# ----------------------
# Models
# ----------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    gender = db.Column(db.String(20))
    dob = db.Column(db.String(20))
    father_name = db.Column(db.String(100))
    mother_name = db.Column(db.String(100))
    category = db.Column(db.String(20))
    pwd = db.Column(db.Integer)
    permanent_address = db.Column(db.String(200))
    current_address = db.Column(db.String(200))
    mobile = db.Column(db.String(15))
    email = db.Column(db.String(100))
    qualification = db.Column(db.String(100))
    course = db.Column(db.String(100))
    specialization = db.Column(db.String(100))
    university = db.Column(db.String(200))
    year_of_passing = db.Column(db.Integer)
    cgpa = db.Column(db.Float)
    skills = db.Column(db.String(500))
    languages = db.Column(db.String(200))
    interests = db.Column(db.String(300))   # comma-separated interests/sectors
    past_experience = db.Column(db.String(500))
    certifications = db.Column(db.String(500))
    hobbies = db.Column(db.String(300))


class Internship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(200))
    title = db.Column(db.String(100))
    required_qualification = db.Column(db.String(100))
    required_skills = db.Column(db.String(500))
    required_languages = db.Column(db.String(200))
    location = db.Column(db.String(100))
    preferred_category = db.Column(db.String(20))
    is_pwd_friendly = db.Column(db.Integer)


class Recommendation(db.Model):
    __tablename__ = "recommendations"
    rec_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    internship_id = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text)
    why_text = db.Column(db.String(300))
    recommended_at = db.Column(db.DateTime, default=datetime.utcnow)


class Application(db.Model):
    __tablename__ = "applications"
    app_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    internship_id = db.Column(db.Integer, nullable=False)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(40), default="applied")

# --- Admin analytics routes (paste into app.py) ---
import os
import io
import csv
from collections import Counter, defaultdict
from flask import Response, render_template_string, request, jsonify, send_file

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", None)

def check_admin_token():
    if not ADMIN_TOKEN:
        return False
    # Accept Authorization header or query param
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token == ADMIN_TOKEN:
            return True
    token_q = request.args.get("token", None)
    if token_q and token_q == ADMIN_TOKEN:
        return True
    return False

def admin_required_json(fn):
    def wrapper(*args, **kwargs):
        if not check_admin_token():
            return jsonify({"error":"unauthorized"}), 401
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper

def admin_required_html(fn):
    def wrapper(*args, **kwargs):
        if not check_admin_token():
            return Response("Unauthorized", status=401)
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper

# Helper: parse comma lists and normalize tokens
def _tokenize_comma_list(s):
    if not s:
        return []
    # split, strip, lower
    parts = [p.strip().lower() for p in s.split(",") if p and p.strip()]
    return parts

# Main admin page (simple inline template using Chart.js)
ADMIN_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Admin — PM Internship Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body{font-family:system-ui,Arial;padding:18px;background:#f8fafc;color:#0f172a}
    .wrap{max-width:1100px;margin:0 auto}
    header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
    .cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
    .card{background:#fff;padding:12px;border-radius:10px;box-shadow:0 6px 18px rgba(2,6,23,0.06);flex:1;min-width:180px}
    canvas{max-width:100%}
    .small{color:#475569;font-size:0.9rem}
    .export{margin-left:8px}
  </style>
</head>
<div style="display:flex;gap:10px;align-items:center;margin-bottom:12px">
  <label class="small">From: <input type="date" id="admin_from" /></label>
  <label class="small">To: <input type="date" id="admin_to" /></label>
  <label class="small">Sector:
    <select id="admin_sector"><option value="">All</option></select>
  </label>
  <label class="small">Category:
    <select id="admin_cat"><option value="">All</option>
      <option>General</option><option>OBC</option><option>SC</option><option>ST</option>
    </select>
  </label>
  <button id="adminRefresh" style="margin-left:8px;">Refresh</button>
</div>

<body>
  <div class="wrap">
    <header>
      <div>
        <h1>PM Internship — Admin Dashboard</h1>
        <div class="small">Quick analytics — token protected</div>
      </div>
      <div>
        <button onclick="window.location='/admin/export/users?token='+token">Export users (CSV)</button>
        <button onclick="window.location='/admin/export/applications?token='+token" class="export">Export applications (CSV)</button>
      </div>
    </header>

    <div class="cards">
      <div class="card"><h3 id="totalUsers">Users: —</h3><div class="small">Total registered users</div></div>
      <div class="card"><h3 id="totalInternships">Internships: —</h3><div class="small">Active internships</div></div>
      <div class="card"><h3 id="totalApplications">Applications: —</h3><div class="small">Total applications</div></div>
      <div class="card"><h3 id="pwdPct">PWD %: —</h3><div class="small">Percent of applicants marked PWD</div></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
      <div class="card">
        <h3>Applicants by Category</h3>
        <canvas id="catChart"></canvas>
      </div>

      <div class="card">
        <h3>Top Skills (Demand)</h3>
        <canvas id="skillChart"></canvas>
      </div>

      <div class="card">
        <h3>Applications Over Time</h3>
        <canvas id="timeChart"></canvas>
      </div>

      <div class="card">
        <h3>Top Internship Sectors</h3>
        <canvas id="sectorChart"></canvas>
      </div>
    </div>
  </div>

<script>
  // Read token from query param so buttons keep it
  function getQueryParam(k){
    const params = new URLSearchParams(window.location.search);
    return params.get(k);
  }
  const token = getQueryParam('token') || '';

  // helper: populate sector dropdown (from server /admin/data?token=.. returns sectors)
async function populateSectorSelect(token){
  try{
    const r = await fetch('/admin/data?token=' + token + '&meta=sectors'); // meta-only request
    if(!r.ok) return;
    const j = await r.json();
    const sel = document.getElementById('admin_sector');
    sel.innerHTML = '<option value="">All</option>';
    (j.sectors && j.sectors.labels || []).forEach(s => {
      const o = document.createElement('option'); o.value = s; o.textContent = s; sel.appendChild(o);
    });
  }catch(e){ console.warn('sector list load failed', e); }
}

function readFilters() {
  const from = document.getElementById('admin_from').value;
  const to = document.getElementById('admin_to').value;
  const sector = document.getElementById('admin_sector').value;
  const category = document.getElementById('admin_cat').value;
  const params = new URLSearchParams();
  if(from) params.append('from', from);
  if(to) params.append('to', to);
  if(sector) params.append('sector', sector);
  if(category) params.append('category', category);
  return params.toString();
}

async function loadData() {
  const tokenParam = token ? ('?token=' + token) : '';
  // populate sectors once
  populateSectorSelect(token);

  // fetch data with filters (first load)
  const qs = readFilters();
  const url = '/admin/data' + (token ? '?token=' + token + (qs ? '&' + qs : '') : (qs ? '?' + qs : ''));
  try {
    const res = await fetch(url);
    if(!res.ok){
      document.body.innerHTML = '<h2>Unauthorized or failed to load admin data</h2>';
      return;
    }
    const data = await res.json();
    // render summary numbers
    document.getElementById('totalUsers').textContent = 'Users: ' + data.totals.users;
    document.getElementById('totalInternships').textContent = 'Internships: ' + data.totals.internships;
    document.getElementById('totalApplications').textContent = 'Applications: ' + data.totals.applications;
    document.getElementById('pwdPct').textContent = 'PWD %: ' + (data.totals.pwd_pct.toFixed(1)) + '%';

    // render charts (reuse existing chart init code or destroy+recreate)
    // simple approach: replace by new Chart objects (ok for admin small-scale)
    const ctx = document.getElementById('catChart').getContext('2d');
    new Chart(ctx, { type:'pie', data:{ labels:data.categories.labels, datasets:[{ data:data.categories.values }] } });

    const kctx = document.getElementById('skillChart').getContext('2d');
    new Chart(kctx, { type:'bar', data:{ labels:data.top_skills.labels, datasets:[{ label:'Mentions', data:data.top_skills.values }] }, options:{ indexAxis:'y' } });

    const tctx = document.getElementById('timeChart').getContext('2d');
    new Chart(tctx, { type:'line', data:{ labels:data.app_time.dates, datasets:[{ label:'Applications', data:data.app_time.counts, fill:true }] } });

    const sctx = document.getElementById('sectorChart').getContext('2d');
    new Chart(sctx, { type:'bar', data:{ labels:data.sectors.labels, datasets:[{ label:'Internships', data:data.sectors.values }] } });

  } catch(e) {
    console.error(e);
    document.body.innerHTML = '<h2>Failed to load admin data</h2>';
  }
}

// wire refresh button
document.getElementById('adminRefresh').addEventListener('click', ()=> loadData());
loadData().catch(e=>console.error(e));
</script>
</body>
</html>
"""

@app.route("/admin")
@admin_required_html
def admin_page():
    # serve inline HTML; admin must pass token in query or header to be allowed in
    return render_template_string(ADMIN_HTML)

# JSON data endpoint for charts & stats
@app.route("/admin/data")
@admin_required_json
def admin_data():
    from datetime import datetime
    # read filters
    from_q = request.args.get('from')
    to_q = request.args.get('to')
    sector_q = request.args.get('sector')
    category_q = request.args.get('category')
    meta_only = request.args.get('meta') == 'sectors'  # for quick sector list

    def parse_date(s):
        if not s: return None
        try:
            return datetime.fromisoformat(s).date()
        except Exception:
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None

    from_date = parse_date(from_q)
    to_date = parse_date(to_q)

    # helper to check if an event's date in range (used for raw fallback)
    def in_range(dt):
        if not dt: return False
        d = dt.date() if hasattr(dt, 'date') else None
        if not d:
            try:
                d = datetime.fromisoformat(dt).date()
            except Exception:
                try:
                    d = datetime.strptime(str(dt), "%Y-%m-%d %H:%M:%S").date()
                except Exception:
                    return False
        if from_date and d < from_date: return False
        if to_date and d > to_date: return False
        return True

    # totals
    totals = {}
    try:
        totals['users'] = db.session.query(User).count()
    except Exception:
        totals['users'] = db.session.execute("SELECT count(*) FROM user").scalar() or 0

    try:
        totals['internships'] = db.session.query(Internship).count()
    except Exception:
        totals['internships'] = db.session.execute("SELECT count(*) FROM internship").scalar() or 0

    # applications and rows (apply filters)
    apps_count = 0
    app_rows = []
    try:
        # SQLAlchemy path
        q = db.session.query(Application)
        if sector_q:
            # filter via join to internship if model present
            try:
                q = q.join(Internship, Application.internship_id == Internship.id).filter(Internship.sector == sector_q)
            except Exception:
                pass
        if category_q:
            try:
                q = q.join(User, Application.user_id == User.id).filter(User.category == category_q)
            except Exception:
                pass
        if from_date:
            q = q.filter(db.func.date(Application.applied_at) >= from_date.isoformat())
        if to_date:
            q = q.filter(db.func.date(Application.applied_at) <= to_date.isoformat())
        app_rows = q.all()
        apps_count = len(app_rows)
    except Exception:
        # raw SQL fallback
        try:
            sql = "SELECT a.app_id, a.user_id, a.internship_id, a.applied_at, a.status FROM application a"
            where = []
            params = {}
            if category_q:
                sql += " JOIN user u ON a.user_id = u.user_id"
                where.append("u.category = :cat")
                params['cat'] = category_q
            if sector_q:
                sql += " JOIN internship i ON a.internship_id = i.id"
                where.append("i.sector = :sector")
                params['sector'] = sector_q
            if from_date:
                where.append("date(a.applied_at) >= :fromd"); params['fromd'] = from_date.isoformat()
            if to_date:
                where.append("date(a.applied_at) <= :tod"); params['tod'] = to_date.isoformat()
            if where:
                sql += " WHERE " + " AND ".join(where)
            raw = db.session.execute(sql, params).fetchall()
            app_rows = raw
            apps_count = len(raw)
        except Exception:
            app_rows = []
            apps_count = 0

    totals['applications'] = apps_count

    # PWD percent (no filters applied here intentionally - stays global)
    try:
        pwd_total = db.session.query(User).filter(User.pwd == 1).count()
        users_total = db.session.query(User).count()
        totals['pwd_pct'] = (pwd_total / users_total * 100) if users_total else 0.0
    except Exception:
        totals['pwd_pct'] = 0.0

    # categories distribution (optionally filter by date/sector using app_rows — we keep simple: base on Users)
    categories = Counter()
    try:
        users = db.session.query(User).all()
        for u in users:
            categories[(u.category or "Unknown")] += 1
    except Exception:
        try:
            rows = db.session.execute("SELECT category FROM user").fetchall()
            for (cat,) in rows:
                categories[cat or "Unknown"] += 1
        except Exception:
            pass

    cat_labels = list(categories.keys())
    cat_values = [categories[k] for k in cat_labels]

    # top skills (respect sector filter by considering internships list)
    skill_counter = Counter()
    sector_counter = Counter()
    try:
        internships_all = db.session.query(Internship).all()
        for it in internships_all:
            sector_counter.update([ (getattr(it,"sector",None) or "Unknown").strip() ])
            if sector_q and ((getattr(it,"sector",None) or "").strip() != sector_q):
                continue
            skills = _tokenize_comma_list(getattr(it, "required_skills", "") or "")
            skill_counter.update(skills)
    except Exception:
        try:
            rows = db.session.execute("SELECT required_skills, sector FROM internship").fetchall()
            for skills_text, sector in rows:
                if sector_q and ((sector or "").strip() != sector_q): continue
                skills = _tokenize_comma_list(skills_text or "")
                skill_counter.update(skills)
                sector_counter.update([ (sector or "Unknown").strip() ])
        except Exception:
            pass

    top_skills = skill_counter.most_common(15)
    top_skills_labels = [k for k,v in top_skills]
    top_skills_values = [v for k,v in top_skills]

    sector_items = sector_counter.most_common(12)
    sector_labels = [k for k,v in sector_items]
    sector_values = [v for k,v in sector_items]

    # applications over time: build counts from app_rows (which already respects filters)
    date_counts = defaultdict(int)
    try:
        for r in app_rows:
            if hasattr(r, "applied_at"):
                dt = getattr(r, "applied_at")
            else:
                dt = r[3] if len(r) > 3 else None
            if not dt: continue
            # normalize to date
            if isinstance(dt, str):
                try:
                    d = datetime.fromisoformat(dt)
                except Exception:
                    try:
                        d = datetime.strptime(str(dt), "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        continue
            else:
                d = dt
            date_counts[d.date().isoformat()] += 1
    except Exception:
        pass

    dates = sorted(date_counts.keys())
    counts = [date_counts[d] for d in dates]

    payload = {
        "totals": totals,
        "categories": {"labels": cat_labels, "values": cat_values},
        "top_skills": {"labels": top_skills_labels, "values": top_skills_values},
        "sectors": {"labels": sector_labels, "values": sector_values},
        "app_time": {"dates": dates, "counts": counts}
    }

    # If meta-only requested, reduce payload size (send only sectors)
    if meta_only:
        return jsonify({"sectors": payload["sectors"]})

    return jsonify(payload)


# CSV export endpoints
@app.route("/admin/export/users")
@admin_required_html
def admin_export_users():
    # stream CSV of users
    try:
        users = db.session.query(User).all()
        output = io.StringIO()
        writer = csv.writer(output)
        header = ["user_id","name","gender","dob","category","pwd","qualification","course","university","year_of_passing","cgpa","skills","languages","created_at","mobile","email"]
        writer.writerow(header)
        for u in users:
            row = [
                getattr(u, "id", ""), getattr(u, "name", ""), getattr(u,"gender",""),
                getattr(u,"dob",""), getattr(u,"category",""), getattr(u,"pwd",""),
                getattr(u,"qualification",""), getattr(u,"course",""), getattr(u,"university",""),
                getattr(u,"year_of_passing",""), getattr(u,"cgpa",""), getattr(u,"skills",""), getattr(u,"languages",""),
                getattr(u,"created_at",""), getattr(u,"mobile",""), getattr(u,"email","")
            ]
            writer.writerow(row)
        output.seek(0)
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=users_export.csv"})
    except Exception as e:
        return Response("Export failed: " + str(e), status=500)

# --- Filterable CSV export: applications ---
from datetime import datetime as _dt

@app.route("/export/applications")
@admin_required_html
def admin_export_applications():
    """
    Export applications as CSV, with optional filters:
      ?token=...            (required for auth)
      &from=YYYY-MM-DD      (optional)  -> applied_at >= from
      &to=YYYY-MM-DD        (optional)  -> applied_at <= to (inclusive)
      &category=OBC         (optional)  -> filter by user's category (if User model exists)
      &internship_id=123    (optional)  -> filter by internship id
    """
    def parse_date(s):
        try:
            return _dt.fromisoformat(s).date()
        except Exception:
            return None

    from_q = request.args.get("from")
    to_q = request.args.get("to")
    category_q = request.args.get("category")
    internship_q = request.args.get("internship_id")

    from_date = parse_date(from_q) if from_q else None
    to_date = parse_date(to_q) if to_q else None

    try:
        # Prefer SQLAlchemy model if available
        try:
            q = db.session.query(Application)
            if internship_q:
                q = q.filter(Application.internship_id == int(internship_q))
            if category_q:
                # join User if model available
                try:
                    q = q.join(User, Application.user_id == User.id).filter(User.category == category_q)
                except Exception:
                    pass
            if from_date:
                # compare date portion of applied_at
                q = q.filter(db.func.date(Application.applied_at) >= from_date.isoformat())
            if to_date:
                q = q.filter(db.func.date(Application.applied_at) <= to_date.isoformat())
            rows = q.all()
            # prepare CSV rows
            output_rows = []
            for a in rows:
                output_rows.append({
                    "app_id": getattr(a, "app_id", getattr(a, "id", "")),
                    "user_id": getattr(a, "user_id", ""),
                    "internship_id": getattr(a, "internship_id", ""),
                    "applied_at": getattr(a, "applied_at", ""),
                    "status": getattr(a, "status", "")
                })
        except Exception:
            # Fallback raw SQL (table 'application' or 'applications')
            # build SQL with parameters
            sql = "SELECT app_id, user_id, internship_id, applied_at, status FROM application WHERE 1=1"
            params = {}
            if internship_q:
                sql += " AND internship_id = :iid"
                params['iid'] = int(internship_q)
            if from_date:
                sql += " AND date(applied_at) >= :fromd"
                params['fromd'] = from_date.isoformat()
            if to_date:
                sql += " AND date(applied_at) <= :tod"
                params['tod'] = to_date.isoformat()
            # category filter requires join with user table
            if category_q:
                # safer: use a join raw query
                sql = ("SELECT a.app_id, a.user_id, a.internship_id, a.applied_at, a.status "
                       "FROM application a JOIN user u ON a.user_id = u.user_id WHERE 1=1")
                if internship_q:
                    sql += " AND a.internship_id = :iid"
                if from_date:
                    sql += " AND date(a.applied_at) >= :fromd"
                if to_date:
                    sql += " AND date(a.applied_at) <= :tod"
                sql += " AND u.category = :category"
                params['category'] = category_q
                if internship_q:
                    params['iid'] = int(internship_q)
                if from_date:
                    params['fromd'] = from_date.isoformat()
                if to_date:
                    params['tod'] = to_date.isoformat()

            raw = db.session.execute(sql, params).fetchall()
            output_rows = []
            for r in raw:
                output_rows.append({
                    "app_id": r[0],
                    "user_id": r[1],
                    "internship_id": r[2],
                    "applied_at": r[3],
                    "status": r[4]
                })

        # Write CSV
        import io, csv
        output = io.StringIO()
        writer = csv.writer(output)
        header = ["app_id","user_id","internship_id","applied_at","status"]
        writer.writerow(header)
        for r in output_rows:
            writer.writerow([r.get(h, "") for h in header])
        output.seek(0)
        fname = "applications_export.csv"
        # add filters info to filename if used
        suffix = []
        if from_q: suffix.append("from-"+from_q)
        if to_q: suffix.append("to-"+to_q)
        if category_q: suffix.append("cat-"+category_q)
        if internship_q: suffix.append("iid-"+str(internship_q))
        if suffix:
            fname = "applications_" + "_".join(suffix) + ".csv"
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename={fname}"})
    except Exception as e:
        return Response("Export failed: " + str(e), status=500)


# --- Admin CSV exports: internships & recommendations ---
import io
import csv
from flask import Response

@app.route("/export/internships")
@admin_required_html
def admin_export_internships():
    """
    Export internships as CSV.
    Columns: internship_id, company_name, title, location, required_qualification,
             required_skills, required_languages, sector, category_preference, pwd_friendly, description, created_at
    """
    try:
        # Try SQLAlchemy model first
        try:
            internships = db.session.query(Internship).all()
            rows = []
            for it in internships:
                rows.append({
                    "internship_id": getattr(it, "id", ""),
                    "company_name": getattr(it, "company_name", ""),
                    "title": getattr(it, "title", ""),
                    "location": getattr(it, "location", ""),
                    "required_qualification": getattr(it, "required_qualification", ""),
                    "required_skills": getattr(it, "required_skills", ""),
                    "required_languages": getattr(it, "required_languages", ""),
                    "sector": getattr(it, "sector", ""),
                    "category_preference": getattr(it, "preferred_category", "") or getattr(it, "category_preference", ""),
                    "pwd_friendly": getattr(it, "is_pwd_friendly", "") or getattr(it, "pwd_friendly", ""),
                    "description": getattr(it, "description", ""),
                    "created_at": getattr(it, "created_at", "")
                })
        except Exception:
            # Fallback raw SQL if model/table name differs
            rows = []
            try:
                raw = db.session.execute(
                    "SELECT id, company_name, title, location, required_qualification, required_skills, required_languages, sector, category_preference, pwd_friendly, description, created_at FROM internship"
                ).fetchall()
                for r in raw:
                    rows.append({
                        "internship_id": r[0],
                        "company_name": r[1],
                        "title": r[2],
                        "location": r[3],
                        "required_qualification": r[4],
                        "required_skills": r[5],
                        "required_languages": r[6],
                        "sector": r[7],
                        "category_preference": r[8],
                        "pwd_friendly": r[9],
                        "description": r[10],
                        "created_at": r[11] if len(r) > 11 else ""
                    })
            except Exception as e:
                return Response("Export failed (no internships): " + str(e), status=500)

        # write CSV
        output = io.StringIO()
        writer = csv.writer(output)
        header = ["internship_id","company_name","title","location","required_qualification","required_skills","required_languages","sector","category_preference","pwd_friendly","description","created_at"]
        writer.writerow(header)
        for r in rows:
            writer.writerow([r.get(h, "") for h in header])
        output.seek(0)
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=internships_export.csv"})
    except Exception as e:
        return Response("Export failed: " + str(e), status=500)


# --- Filterable CSV export: recommendations ---
@app.route("/export/recommendations")
@admin_required_html
def admin_export_recommendations():
    """
    Export recommendations/recommendation log as CSV, with optional filters:
      ?from=YYYY-MM-DD   (applied / recommended date lower bound)
      ?to=YYYY-MM-DD
      ?sector=IT         (filter by internship sector)
      ?internship_id=123
    """
    def parse_date(s):
        try:
            return _dt.fromisoformat(s).date()
        except Exception:
            return None

    from_q = request.args.get("from")
    to_q = request.args.get("to")
    sector_q = request.args.get("sector")
    internship_q = request.args.get("internship_id")

    from_date = parse_date(from_q) if from_q else None
    to_date = parse_date(to_q) if to_q else None

    try:
        # Try SQLAlchemy model named Recommendation first (if exists)
        found = False
        output_rows = []

        RecModel = globals().get("Recommendation") or globals().get("recommendation")
        if RecModel:
            try:
                q = db.session.query(RecModel)
                if internship_q:
                    q = q.filter(RecModel.internship_id == int(internship_q))
                if from_date:
                    q = q.filter(db.func.date(RecModel.recommended_at) >= from_date.isoformat())
                if to_date:
                    q = q.filter(db.func.date(RecModel.recommended_at) <= to_date.isoformat())
                rows = q.all()
                for r in rows:
                    output_rows.append({
                        "rec_id": getattr(r,"rec_id", getattr(r,"id","")),
                        "user_id": getattr(r,"user_id",""),
                        "internship_id": getattr(r,"internship_id",""),
                        "score": getattr(r,"score",""),
                        "reason": getattr(r,"reason",""),
                        "recommended_at": getattr(r,"recommended_at", getattr(r,"created_at",""))
                    })
                found = True
            except Exception:
                found = False

        if not found:
            # fallback: try to join recommendations -> internship to filter by sector (raw SQL)
            # common table name guesses for recommendations
            tried_tables = ["recommendations", "recommendation", "recommendation_log", "recommendation_logs"]
            success = False
            for tbl in tried_tables:
                try:
                    # build base query
                    sql = f"SELECT r.rec_id, r.user_id, r.internship_id, r.score, r.reason, r.recommended_at, i.sector FROM {tbl} r LEFT JOIN internship i ON r.internship_id = i.id WHERE 1=1"
                    params = {}
                    if internship_q:
                        sql += " AND r.internship_id = :iid"
                        params['iid'] = int(internship_q)
                    if sector_q:
                        sql += " AND lower(i.sector) = lower(:sector)"
                        params['sector'] = sector_q
                    if from_date:
                        sql += " AND date(r.recommended_at) >= :fromd"
                        params['fromd'] = from_date.isoformat()
                    if to_date:
                        sql += " AND date(r.recommended_at) <= :tod"
                        params['tod'] = to_date.isoformat()
                    raw = db.session.execute(sql, params).fetchall()
                    if raw:
                        success = True
                        for r in raw:
                            output_rows.append({
                                "rec_id": r[0],
                                "user_id": r[1],
                                "internship_id": r[2],
                                "score": r[3],
                                "reason": r[4],
                                "recommended_at": r[5]
                            })
                        break
                except Exception:
                    continue

            if not success and not output_rows:
                return Response("No recommendations table found or no rows for filters", status=404)

        # write CSV
        import io, csv
        output = io.StringIO()
        writer = csv.writer(output)
        header = ["rec_id","user_id","internship_id","score","reason","recommended_at"]
        writer.writerow(header)
        for r in output_rows:
            writer.writerow([r.get(h, "") for h in header])
        output.seek(0)
        # filename suffix
        fname = "recommendations_export.csv"
        suffix = []
        if from_q: suffix.append("from-"+from_q)
        if to_q: suffix.append("to-"+to_q)
        if sector_q: suffix.append("sector-"+sector_q)
        if internship_q: suffix.append("iid-"+str(internship_q))
        if suffix: fname = "recommendations_" + "_".join(suffix) + ".csv"
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":f"attachment;filename={fname}"})
    except Exception as e:
        return Response("Export failed: " + str(e), status=500)

# ----------------------
# Helpers
# ----------------------
def score_label(score):
    if score >= 70:
        return "✅ Strong Match"
    if score >= 50:
        return "⚠️ Medium Match"
    return "❌ Weak Match"


def _build_simple_list(recs):
    simple = []
    for r in recs:
        bd = r.get("score_breakdown", {}) or {}
        matched_skills = bd.get("matched_skills", []) or []
        matched_langs = bd.get("matched_languages", []) or []
        parts = []
        if matched_skills:
            parts.append("Matched skills: " + ", ".join(matched_skills))
        if matched_langs:
            parts.append("Matched languages: " + ", ".join(matched_langs))
        if bd.get("location", 0) > 0:
            parts.append("Location matched")
        if bd.get("inclusiveness", 0) > 0:
            parts.append("Inclusiveness bonus applied")
        why = "; ".join(parts) if parts else "Basic match"

        simple.append({
            "Internship Title": r.get("title"),
            "Company": r.get("company_name"),
            "Location": r.get("location"),
            "Score": r.get("score"),
            "Match Level": score_label(r.get("score", 0)),
            "Matched Skills": ", ".join(matched_skills) if matched_skills else None,
            "Matched Languages": ", ".join(matched_langs) if matched_langs else None,
            "Why": why,
            "internship_id": r.get("internship_id")
        })
    return simple

# app.py — add this route (requires existing Application, Internship, Recommendation, User models)
@app.route("/applications/<int:user_id>", methods=["GET"])
def get_applications_for_user(user_id):
    # Optional admin token could be added, but for now it's public for the user
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404

    apps = Application.query.filter_by(user_id=user_id).order_by(Application.applied_at.desc()).all()
    out = []
    for a in apps:
        intern = Internship.query.get(a.internship_id)
        out.append({
            "app_id": a.app_id,
            "user_id": a.user_id,
            "internship_id": a.internship_id,
            "applied_at": a.applied_at.isoformat(),
            "status": a.status,
            "internship": {
                "company_name": getattr(intern, "company_name", None),
                "title": getattr(intern, "title", None),
                "location": getattr(intern, "location", None),
                "required_qualification": getattr(intern, "required_qualification", None),
                "required_skills": getattr(intern, "required_skills", None),
                "required_languages": getattr(intern, "required_languages", None)
            },
            # optionally include a small snapshot of user's profile at time of application:
            "user_snapshot": {
                "name": user.name,
                "mobile": user.mobile,
                "email": user.email,
                "qualification": user.qualification,
                "skills": user.skills,
                "languages": user.languages,
                "category": user.category,
                "pwd": user.pwd
            }
        })
    return jsonify(out)

def _log_recommendations(user_id, recs):
    try:
        for r in recs:
            bd = r.get("score_breakdown", {}) or {}
            matched_skills = bd.get("matched_skills", []) or []
            matched_langs = bd.get("matched_languages", []) or []
            parts = []
            if matched_skills:
                parts.append("Matched skills: " + ", ".join(matched_skills))
            if matched_langs:
                parts.append("Matched languages: " + ", ".join(matched_langs))
            if bd.get("location", 0) > 0:
                parts.append("Location matched")
            if bd.get("inclusiveness", 0) > 0:
                parts.append("Inclusiveness bonus applied")
            why_text = "; ".join(parts) if parts else "Basic match"

            rec = Recommendation(
                user_id=user_id,
                internship_id=r.get("internship_id"),
                score=r.get("score", 0.0),
                reason=json.dumps(bd, default=str),
                why_text=why_text
            )
            db.session.add(rec)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("Failed to write recommendation logs:", e)


# ----------------------
# Routes
# ----------------------
@app.route("/recommend/<int:user_id>", methods=["GET","POST"])
def get_recommendations(user_id):
    # support GET or POST body
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        n = data.get("n", 5)
        min_score = data.get("min_score", 40)
    else:
        n = request.args.get("n", default=5, type=int)
        min_score = request.args.get("min_score", default=40, type=int)

    recs = recommend_for_user_id(user_id, top_n=n, min_score=min_score)
    return jsonify(recs)


@app.route("/recommend", methods=["POST"])
def recommend_post():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "send user_id in JSON body"}), 400

    n = int(data.get("n", 5))
    min_score = float(data.get("min_score", 40))
    debug = bool(data.get("debug", False))

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404

    internships = Internship.query.all()
    recs = recommend_internships_for_user(user, internships, top_n=n, min_score=min_score)
    _log_recommendations(user_id, recs)
    if debug:
        return jsonify(recs)
    return jsonify(_build_simple_list(recs))

@app.route("/admin/rebuild_tfidf", methods=["POST","GET"])
@admin_required_html
def admin_rebuild_tfidf_route():
    maxf = request.args.get("max_features", None)
    res = rebuild_tfidf(max_features=maxf)
    return jsonify(res)

@app.route("/admin/tfidf_status")
@admin_required_json
def admin_tfidf_status():
    return jsonify(tfidf_status())


from flask import abort

@app.route("/add_user", methods=["POST"])
def add_user():
    data = request.json or {}

    # whitelist of allowed User fields (update if you add/remove columns)
    allowed = {
        "name","gender","dob","father_name","mother_name","category","pwd",
        "permanent_address","current_address","mobile","email","qualification",
        "course","specialization","university","year_of_passing","cgpa",
        "skills","languages","interests","past_experience","certifications","hobbies"
    }

    def parse_cgpa(value):
        if value is None or value == "":
            return None
        # Accept numbers, strings like "89%", "7.8", "89", "89.0"
        try:
            s = str(value).strip()
            # If contains percent sign, strip and treat as percentage (e.g., "89%" -> 89.0)
            if s.endswith("%"):
                s = s.rstrip("%").strip()
                return float(s)
            # If a value looks like percentage but without %, we still parse float
            return float(s)
        except Exception:
            # if everything fails, raise ValueError to signal bad input
            raise ValueError(f"Invalid cgpa/grade value: {value}")

    def parse_year(y):
        if y is None or y == "":
            return None
        try:
            return int(float(y))
        except Exception:
            raise ValueError(f"Invalid year_of_passing: {y}")

    # filter incoming data by allowed keys
    filtered = {k: v for k, v in data.items() if k in allowed}

    # parse/coerce some fields safely
    # pwd -> integer 0/1
    if "pwd" in filtered:
        try:
            filtered["pwd"] = 1 if int(filtered["pwd"]) else 0
        except Exception:
            # accept "yes"/"no" strings as well
            val = str(filtered["pwd"]).strip().lower()
            filtered["pwd"] = 1 if val in ("1","true","yes","y") else 0

    # year_of_passing -> int
    if "year_of_passing" in filtered:
        try:
            filtered["year_of_passing"] = parse_year(filtered.get("year_of_passing"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    # cgpa -> float (strip % and other text)
    if "cgpa" in filtered:
        try:
            cgpa_val = filtered.get("cgpa")
            filtered["cgpa"] = parse_cgpa(cgpa_val)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    # Construct User only with allowed, sanitized fields
    try:
        user = User(**filtered)
    except TypeError as e:
        # defensive: should not happen because we filtered keys, but return useful message
        return jsonify({"error": "Invalid user data: " + str(e)}), 400

    db.session.add(user)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "DB error: " + str(e)}), 500

    return jsonify({"message": "User added", "user_id": user.id})


@app.route("/add_internship", methods=["POST"])
def add_internship():
    data = request.json or {}
    internship = Internship(**data)
    db.session.add(internship)
    db.session.commit()

    # Non-blocking rebuild of TF-IDF cache to avoid delaying the API response.
    def _rebuild_cache_async():
        try:
            build_tfidf_cache(Internship.query.all())
            print("TF-IDF cache rebuilt (async).")
        except Exception as e:
            print("Error rebuilding TF-IDF cache (async):", e)

    try:
        t = threading.Thread(target=_rebuild_cache_async, daemon=True)
        t.start()
    except Exception as e:
        # fallback: try synchronous rebuild if thread creation fails
        try:
            build_tfidf_cache(Internship.query.all())
            print("TF-IDF cache rebuilt (sync fallback).")
        except Exception as ex:
            print("TF-IDF cache rebuild failed:", ex)

    return jsonify({"message": "Internship added", "internship_id": internship.id})


# POST /apply
@app.route("/apply", methods=["POST"])
def apply():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "send JSON body with user_id and internship_id"}), 400

    user_id = data.get("user_id")
    internship_id = data.get("internship_id")
    if user_id is None or internship_id is None:
        return jsonify({"error": "send user_id and internship_id"}), 400

    try:
        user_id = int(user_id)
        internship_id = int(internship_id)
    except Exception:
        return jsonify({"error": "user_id and internship_id must be integers"}), 400

    # verify existence
    user = User.query.get(user_id)
    internship = Internship.query.get(internship_id)
    if not user or not internship:
        return jsonify({"error": "user or internship not found"}), 404

    # prevent duplicate application
    from sqlalchemy import and_
    existing = None
    try:
        existing = Application.query.filter_by(user_id=user_id, internship_id=internship_id).first()
    except Exception:
        # If Application model/table missing, create simple fallback insertion
        existing = None

    if existing:
        return jsonify({"message": "already applied", "application_id": existing.app_id}), 200

    # create application record (ensure Application model exists in your app)
    try:
        app_row = Application(user_id=user_id, internship_id=internship_id, applied_at=datetime.utcnow(), status="applied")
        db.session.add(app_row)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "db_error", "details": str(e)}), 500

    # optional: return helpful detail for client-side UI
    return jsonify({
        "message": "applied",
        "application_id": app_row.app_id,
        "user_id": user_id,
        "internship_id": internship_id,
        "applied_at": app_row.applied_at.isoformat()
    }), 201


# POST /withdraw
@app.route("/withdraw", methods=["POST"])
def withdraw():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "send JSON body with user_id and internship_id"}), 400

    user_id = data.get("user_id")
    internship_id = data.get("internship_id")
    if user_id is None or internship_id is None:
        return jsonify({"error": "send user_id and internship_id"}), 400

    try:
        user_id = int(user_id)
        internship_id = int(internship_id)
    except Exception:
        return jsonify({"error": "user_id and internship_id must be integers"}), 400

    application = Application.query.filter_by(user_id=user_id, internship_id=internship_id).first()
    if not application:
        return jsonify({"error": "application not found"}), 404

    try:
        application.status = "withdrawn"
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error":"db_error","details":str(e)}), 500

    return jsonify({"message":"withdrawn","application_id":application.app_id}), 200



@app.route("/recommendations/logs", methods=["GET"])
def view_recommendation_logs():
    admin_token = app.config.get("ADMIN_TOKEN", None)
    header_token = request.headers.get("X-ADMIN-TOKEN")
    if not admin_token or header_token != admin_token:
        return jsonify({"error": "unauthorized"}), 401
    limit = int(request.args.get("limit", 50))
    logs = Recommendation.query.order_by(Recommendation.recommended_at.desc()).limit(limit).all()
    out = []
    for l in logs:
        reason_obj = None
        try:
            reason_obj = json.loads(l.reason) if l.reason else None
        except Exception:
            reason_obj = l.reason
        out.append({
            "rec_id": l.rec_id,
            "user_id": l.user_id,
            "internship_id": l.internship_id,
            "score": l.score,
            "why_text": l.why_text,
            "reason": reason_obj,
            "recommended_at": l.recommended_at.isoformat()
        })
    return jsonify(out)


# serve widget from static folder if present
@app.route("/widget")
def widget():
    return send_from_directory(os.path.join(app.root_path, "static"), "widget.html")


from engine import init_engine, recommend_for_user_id, rebuild_tfidf, tfidf_status
init_engine(app, db, User, Internship, Application)

# ----------------------
# Init DB & run
# ----------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # build tf-idf cache once at startup (synchronous)
        try:
            build_tfidf_cache(Internship.query.all())
            print("TF-IDF cache built at startup.")
        except Exception as e:
            print("TF-IDF cache build failed at startup:", e)

    app.run(debug=True)
