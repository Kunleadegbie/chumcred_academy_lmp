# app.py — Chumcred Academy LMP (full working code with edit/delete materials + Week 2–6 seeding)
import os
import io
import sqlite3
import datetime as dt
from pathlib import Path

import streamlit as st
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import bcrypt

APP_TITLE = os.getenv("APP_TITLE", "Chumcred Academy — AI Essentials LMP")
BASE = Path(".")
DB_PATH = BASE / "lmp.db"
UPLOADS_DIR = BASE / "uploads"
ASSETS_DIR = BASE / "assets"
for d in (UPLOADS_DIR, ASSETS_DIR):
    d.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title=APP_TITLE, page_icon="🎓", layout="wide")

# ----------------------------- Secrets Helpers -----------------------------
def get_secret(key: str, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return os.getenv(key, default)

# ----------------------------- DB Helpers -----------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def run_ddl():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT,
            role TEXT NOT NULL CHECK(role IN ('admin','student')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            kind TEXT NOT NULL, -- 'file' or 'link'
            path_or_url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (module_id) REFERENCES modules(id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            prompt TEXT,
            due_date TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (module_id) REFERENCES modules(id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            file_path TEXT,
            text_response TEXT,
            submitted_at TEXT NOT NULL,
            grade REAL,
            feedback TEXT,
            graded_at TEXT,
            graded_by INTEGER,
            FOREIGN KEY (assignment_id) REFERENCES assignments(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (graded_by) REFERENCES users(id)
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_submission ON submissions(assignment_id, user_id)
    """)
    conn.commit()
    conn.close()

# ----------------------------- Seed Data -----------------------------
def ensure_seed():
    conn = get_conn()
    cur = conn.cursor()

    # Seed admin
    cur.execute("SELECT COUNT(1) FROM users")
    if cur.fetchone()[0] == 0:
        admin_user = get_secret("ADMIN_USERNAME", "admin")
        admin_pwd = get_secret("ADMIN_PASSWORD", "Admin@123")
        hashed = bcrypt.hashpw(admin_pwd.encode("utf-8"), bcrypt.gensalt())
        cur.execute("""
            INSERT INTO users(username, password_hash, full_name, email, role, active, created_at)
            VALUES(?,?,?,?,?,?,?)
        """, (admin_user, hashed, "System Administrator", "admin@chumcred.academy", "admin", 1, dt.datetime.utcnow().isoformat()))
        st.session_state["__seed_notice__"] = f"Default admin → `{admin_user}` / `{admin_pwd}` (change after first login)."

    # Seed modules & assignments
    cur.execute("SELECT COUNT(1) FROM modules")
    if cur.fetchone()[0] == 0:
        modules = [
            (1, "Introduction to AI & Workplace Applications",
             "Core AI concepts, responsible AI, and cross-industry case studies (telecoms, sales, credit, finance, analytics)."),
            (2, "AI for Sales & Customer Engagement",
             "AI CRM, predictive lead scoring, churn management, and conversational AI for customer support."),
            (3, "AI in Credit & Finance",
             "Credit scoring, fraud/anomaly detection, forecasting, compliance and governance in AI."),
            (4, "AI for Data Analysis & Business Intelligence",
             "AI-assisted analytics with Excel/Power BI, NLP for text data, and data storytelling."),
            (5, "AI in Telecoms & Network Optimization",
             "Predictive maintenance, ARPU optimization, churn reduction, and retail expansion insights."),
            (6, "Capstone & Future of AI at Work",
             "Generative AI, AutoML, AI in 5G/IoT, best practices, and career pathways. Capstone showcase.")
        ]
        for w, t, d in modules:
            cur.execute("INSERT INTO modules(week_number, title, description, created_at) VALUES(?,?,?,?)",
                        (w, t, d, dt.datetime.utcnow().isoformat()))

        cur.execute("SELECT id, week_number FROM modules ORDER BY week_number")
        for m in cur.fetchall():
            wk = m["week_number"]
            prompts = {
                1: "Identify three job tasks you will enhance with AI and outline an adoption plan (tools, expected gain, risks).",
                2: "Build a customer segmentation and draft an AI-driven sales script for a chosen segment.",
                3: "Create a credit risk dashboard highlighting risky vs safe clients. Explain your approach in 200 words.",
                4: "Analyze a dataset using Power BI/Excel AI. Submit a dashboard + 1-page executive summary.",
                5: "Using telecom KPIs (RGB, ARPU, BTS), identify high-growth regions and recommend actions.",
                6: "Capstone: Propose and present an AI-powered solution for a real business problem in your domain."
            }
            due = (dt.date.today() + dt.timedelta(days=7*wk)).isoformat()
            cur.execute("""
                INSERT INTO assignments(module_id, title, prompt, due_date, created_at)
                VALUES(?,?,?,?,?)
            """, (m["id"], f"Week {wk} Assignment", prompts[wk], due, dt.datetime.utcnow().isoformat()))

    # ---------- Idempotent helper to seed materials ----------
    def _seed_week_materials(week_number, items):
        """
        items: list of tuples (title, kind, path_or_url)
               kind ∈ {'link', 'file'}
        """
        cur.execute("SELECT id FROM modules WHERE week_number=?", (week_number,))
        row = cur.fetchone()
        if not row:
            return
        module_id = row["id"]
        for title, kind, path in items:
            cur.execute("""
                SELECT 1 FROM materials
                WHERE module_id=? AND title=? AND kind=? AND path_or_url=?
            """, (module_id, title, kind, path))
            exists = cur.fetchone()
            if not exists:
                cur.execute("""
                    INSERT INTO materials(module_id, title, kind, path_or_url, created_at)
                    VALUES(?,?,?,?,?)
                """, (module_id, title, kind, path, dt.datetime.utcnow().isoformat()))

    # Week 1 (existing)
    cur.execute("SELECT id FROM modules WHERE week_number=1")
    row = cur.fetchone()
    if row:
        _seed_week_materials(1, [
            ("OECD AI Principles (overview)", "link", "https://oecd.ai/en/ai-principles"),
            ("Microsoft Responsible AI Standard (overview)", "link", "https://www.microsoft.com/en-us/ai/responsible-ai"),
            ("Power BI Documentation", "link", "https://learn.microsoft.com/power-bi/"),
            ("Streamlit Docs", "link", "https://docs.streamlit.io/"),
        ])

    # Week 2 — AI for Sales & Customer Engagement
    _seed_week_materials(2, [
        ("Salesforce Einstein Overview", "link", "https://www.salesforce.com/products/einstein/overview/"),
        ("HubSpot AI Features", "link", "https://www.hubspot.com/products/ai"),
        ("Churn Prediction (Concepts & Examples)", "link", "https://en.wikipedia.org/wiki/Customer_attrition"),
        ("Conversational AI: Design Best Practices", "link", "https://cloud.google.com/architecture/dialogflow-design"),
        ("Power BI: Customer Segmentation Tutorial", "link", "https://learn.microsoft.com/power-bi/consumer/end-user-segmentation"),
    ])

    # Week 3 — AI in Credit & Finance
    _seed_week_materials(3, [
        ("Credit Scoring Basics (PD/LGD/EAD)", "link", "https://en.wikipedia.org/wiki/Credit_scoring"),
        ("Anomaly & Fraud Detection Guide (sklearn)", "link", "https://scikit-learn.org/stable/modules/outlier_detection.html"),
        ("Time Series Forecasting (Intro)", "link", "https://otexts.com/fpp3/"),
        ("Model Risk Management (General Concepts)", "link", "https://en.wikipedia.org/wiki/Model_risk"),
        ("Pandas + Finance Basics", "link", "https://pandas.pydata.org/docs/user_guide/index.html"),
    ])

    # Week 4 — AI for Data Analysis & BI
    _seed_week_materials(4, [
        ("Power BI Learning Path", "link", "https://learn.microsoft.com/power-bi/"),
        ("Excel with Copilot (Overview)", "link", "https://support.microsoft.com/en-us/office/get-started-with-copilot-in-excel"),
        ("NLP 101 (Tokenization → Sentiment → Topics)", "link", "https://scikit-learn.org/stable/tutorial/text_analytics/working_with_text.html"),
        ("Tableau: Get Started", "link", "https://www.tableau.com/learn/training"),
        ("Data Storytelling Patterns", "link", "https://www.data-to-viz.com/"),
    ])

    # Week 5 — AI in Telecoms & Network Optimization
    _seed_week_materials(5, [
        ("AI for Predictive Maintenance (Intro)", "link", "https://en.wikipedia.org/wiki/Predictive_maintenance"),
        ("Telecom Churn Use-Cases (Overview)", "link", "https://www.ibm.com/docs/en/cognos-analytics/11.1.0?topic=applications-customer-churn"),
        ("Time Series for KPIs (ARPU/Usage)", "link", "https://otexts.com/fpp3/forecasting.html"),
        ("Geospatial in Power BI", "link", "https://learn.microsoft.com/power-bi/visuals/power-bi-map-tips-and-tricks"),
        ("Network Optimization (Concepts)", "link", "https://en.wikipedia.org/wiki/Network_optimization"),
    ])

    # Week 6 — Capstone & Future of AI at Work
    _seed_week_materials(6, [
        ("Intro to Generative AI (High level)", "link", "https://cloud.google.com/learn/what-is-generative-ai"),
        ("AutoML Concepts", "link", "https://en.wikipedia.org/wiki/Automated_machine_learning"),
        ("MLOps Overview", "link", "https://www.microsoft.com/en-us/research/project/mlops/"),
        ("Responsible AI Playbook (General)", "link", "https://ai.google/responsibility/"),
        ("Presentation Best Practices", "link", "https://www.duarte.com/presentation-skills-resources/"),
    ])

    conn.commit()
    conn.close()

# ----------------------------- Auth -----------------------------
def hash_password(pw: str) -> bytes:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt())

def verify_password(pw: str, hashed: bytes) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed)
    except Exception:
        return False

def get_user_by_username(username: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    return row

def create_user(username, password, full_name, email, role="student"):
    conn = get_conn()
    cur = conn.cursor()
    pwd_hash = hash_password(password)
    cur.execute("""
        INSERT INTO users(username, password_hash, full_name, email, role, active, created_at)
        VALUES(?,?,?,?,?,?,?)
    """, (username, pwd_hash, full_name, email, role, 1, dt.datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def update_password(user_id: int, current_pw: str, new_pw: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "User not found."
    if not verify_password(current_pw, row["password_hash"]):
        conn.close()
        return False, "Current password is incorrect."
    cur.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new_pw), user_id))
    conn.commit()
    conn.close()
    return True, "Password updated."

# ----------------------------- Data Access -----------------------------
def fetch_modules():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM modules ORDER BY week_number")
    rows = cur.fetchall()
    conn.close()
    return rows

def fetch_materials(module_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM materials WHERE module_id=? ORDER BY id", (module_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def add_material(module_id: int, title: str, kind: str, path_or_url: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO materials(module_id, title, kind, path_or_url, created_at)
        VALUES(?,?,?,?,?)
    """, (module_id, title, kind, path_or_url, dt.datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def delete_material(material_id: int):
    conn = get_conn()
    cur = conn.cursor()
    # Try to remove local file if this was a 'file' kind
    cur.execute("SELECT kind, path_or_url FROM materials WHERE id=?", (material_id,))
    row = cur.fetchone()
    if row and row["kind"] == "file":
        fp = row["path_or_url"]
        try:
            if os.path.exists(fp):
                os.remove(fp)
        except Exception:
            pass
    cur.execute("DELETE FROM materials WHERE id=?", (material_id,))
    conn.commit()
    conn.close()

def update_material(material_id: int, title: str, kind: str = None, path_or_url: str = None):
    conn = get_conn()
    cur = conn.cursor()
    if kind is None and path_or_url is None:
        cur.execute("UPDATE materials SET title=? WHERE id=?", (title, material_id))
    elif kind is None:
        cur.execute("UPDATE materials SET title=?, path_or_url=? WHERE id=?", (title, path_or_url, material_id))
    elif path_or_url is None:
        cur.execute("UPDATE materials SET title=?, kind=? WHERE id=?", (title, kind, material_id))
    else:
        cur.execute("UPDATE materials SET title=?, kind=?, path_or_url=? WHERE id=?", (title, kind, path_or_url, material_id))
    conn.commit()
    conn.close()

def fetch_assignments(module_id: int = None):
    conn = get_conn()
    cur = conn.cursor()
    if module_id is None:
        cur.execute("""
            SELECT a.*, m.week_number
            FROM assignments a JOIN modules m ON a.module_id=m.id
            ORDER BY m.week_number
        """)
    else:
        cur.execute("""
            SELECT a.*, m.week_number
            FROM assignments a JOIN modules m ON a.module_id=m.id
            WHERE module_id=? ORDER BY a.id
        """, (module_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def add_assignment(module_id: int, title: str, prompt: str, due_date: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO assignments(module_id, title, prompt, due_date, created_at)
        VALUES(?,?,?,?,?)
    """, (module_id, title, prompt, due_date, dt.datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_submission(assignment_id: int, user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM submissions WHERE assignment_id=? AND user_id=?", (assignment_id, user_id))
    row = cur.fetchone()
    conn.close()
    return row

def upsert_submission(assignment_id: int, user_id: int, file_path: str, text_response: str):
    conn = get_conn()
    cur = conn.cursor()
    now = dt.datetime.utcnow().isoformat()
    # Use a direct check to avoid nested connections in get_submission()
    cur.execute("SELECT id FROM submissions WHERE assignment_id=? AND user_id=?", (assignment_id, user_id))
    existing = cur.fetchone()
    if existing:
        cur.execute("""
            UPDATE submissions SET file_path=?, text_response=?, submitted_at=?
            WHERE assignment_id=? AND user_id=?
        """, (file_path, text_response, now, assignment_id, user_id))
    else:
        cur.execute("""
            INSERT INTO submissions(assignment_id, user_id, file_path, text_response, submitted_at)
            VALUES(?,?,?,?,?)
        """, (assignment_id, user_id, file_path, text_response, now))
    conn.commit()
    conn.close()

def grade_submission(submission_id: int, grade: float, feedback: str, grader_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE submissions SET grade=?, feedback=?, graded_at=?, graded_by=?
        WHERE id=?
    """, (grade, feedback, dt.datetime.utcnow().isoformat(), grader_id, submission_id))
    conn.commit()
    conn.close()

def fetch_ungraded_submissions():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.*, a.title as assignment_title, m.week_number, u.full_name as student_name
        FROM submissions s
        JOIN assignments a ON s.assignment_id=a.id
        JOIN modules m ON a.module_id=m.id
        JOIN users u ON s.user_id=u.id
        WHERE s.grade IS NULL
        ORDER BY s.submitted_at DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def fetch_user_submissions(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.*, a.title as assignment_title, m.week_number
        FROM submissions s
        JOIN assignments a ON s.assignment_id=a.id
        JOIN modules m ON a.module_id=m.id
        WHERE s.user_id=?
        ORDER BY m.week_number
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def fetch_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, full_name, email, role, active, created_at FROM users ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return rows

def set_user_active(user_id: int, active: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET active=? WHERE id=?", (active, user_id))
    conn.commit()
    conn.close()

# ----------------------------- Certificates -----------------------------
def eligible_for_certificate(user_id: int):
    subs = fetch_user_submissions(user_id)
    by_week = {r["week_number"]: r for r in subs}
    if len(by_week) < 6:
        return False, 0.0
    grades = [r["grade"] for r in subs if r["grade"] is not None]
    if len(grades) < 6:
        return False, 0.0
    avg = sum(grades) / len(grades)
    return avg >= 60.0, avg

def generate_certificate_pdf(student_name: str, certificate_id: str):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Border
    c.setStrokeColor(colors.HexColor("#2A4365"))
    c.setLineWidth(5)
    c.rect(40, 40, width-80, height-80, stroke=1, fill=0)

    # Title
    c.setFont("Helvetica-Bold", 26)
    c.setFillColor(colors.HexColor("#2A4365"))
    c.drawCentredString(width/2, height-90, "Certificate of Completion")

    # Body
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    lines = [
        "This certifies that",
        "",
        student_name,
        "",
        "has successfully completed the program",
        "",
        "AI Essentials for Effectiveness in Telecoms, Sales, Credit, Finance & Data Analysis",
        "",
        "organized by Chumcred Academy."
    ]
    y = height - 150
    for line in lines:
        c.drawCentredString(width/2, y, line)
        y -= 22

    # Footer
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(60, 60, f"Issued on: {dt.date.today().isoformat()}")
    c.drawRightString(width-60, 60, f"Certificate ID: {certificate_id}")
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# ----------------------------- UI Components -----------------------------
def login_form():
    st.subheader("Sign In")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login", use_container_width=True):
        user = get_user_by_username(username.strip())
        if user and user["active"] == 1 and verify_password(password, user["password_hash"]):
            st.session_state["user"] = dict(user)
            st.success(f"Welcome, {user['full_name']}")
            st.rerun()
        else:
            st.error("Invalid credentials or inactive account.")

def logout_button():
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.pop("user", None)
        st.rerun()

def admin_create_user_ui():
    st.subheader("Create New User")
    col1, col2 = st.columns(2)
    with col1:
        full_name = st.text_input("Full name")
        username = st.text_input("Username (unique)")
        email = st.text_input("Email")
    with col2:
        role = st.selectbox("Role", ["student", "admin"])
        temp_password = st.text_input("Temporary Password", help="Share this with the user securely.")
    if st.button("Create User"):
        if full_name and username and temp_password:
            try:
                create_user(username, temp_password, full_name, email, role)
                st.success(f"User created for {full_name}.")
            except Exception as e:
                st.error(f"Error creating user: {e}")
        else:
            st.warning("Please fill all required fields.")

def admin_users_table():
    st.subheader("All Users")
    users = fetch_users()
    df = pd.DataFrame(users)
    st.dataframe(df, use_container_width=True, height=300)
    for u in users:
        c1, c2 = st.columns([6,1])
        with c1:
            st.write(f"**{u['full_name']}** — @{u['username']} — {u['email']} — *{u['role']}* — {'Active' if u['active'] else 'Inactive'}")
        with c2:
            if st.button(("Deactivate" if u["active"] else "Activate"), key=f"act_{u['id']}"):
                set_user_active(u["id"], 0 if u["active"] else 1)
                st.rerun()

def student_modules_ui(user):
    st.header("Course Modules")
    modules = fetch_modules()
    for m in modules:
        with st.expander(f"Week {m['week_number']}: {m['title']}", expanded=False):
            st.write(m["description"] or "")
            mats = fetch_materials(m["id"])
            if mats:
                st.write("**Materials**")
                for mat in mats:
                    if mat["kind"] == "link":
                        st.markdown(f"- 🔗 [{mat['title']}]({mat['path_or_url']})")
                    else:
                        fp = mat["path_or_url"]
                        name = os.path.basename(fp)
                        try:
                            with open(fp, "rb") as f:
                                st.download_button(f"Download: {mat['title']}", f.read(), file_name=name, key=f"d_{mat['id']}")
                        except Exception:
                            st.warning(f"File not found: {name}")
            assigns = fetch_assignments(m["id"])
            if assigns:
                st.write("**Assignment**")
                for a in assigns:
                    st.write(f"**{a['title']}** — Due: {a['due_date']}")
                    existing = get_submission(a["id"], user["id"])
                    if existing:
                        st.success(f"Submitted on {existing['submitted_at']}")
                        if existing["grade"] is not None:
                            st.info(f"Grade: {existing['grade']:.1f} | Feedback: {existing['feedback'] or '—'}")
                    with st.form(key=f"subm_{a['id']}"):
                        st.write("Submit/Update your work:")
                        upl = st.file_uploader("Upload file (optional)", type=["pdf","pptx","docx","xlsx","csv","zip","png","jpg","ipynb"], key=f"f_{a['id']}")
                        text_resp = st.text_area("Short write-up (optional)", height=120, key=f"t_{a['id']}")
                        if st.form_submit_button("Submit"):
                            save_path = None
                            if upl is not None:
                                save_path = str((UPLOADS_DIR / f"user{user['id']}_a{a['id']}_{upl.name}").resolve())
                                with open(save_path, "wb") as f:
                                    f.write(upl.getbuffer())
                            upsert_submission(a["id"], user["id"], save_path, text_resp.strip() if text_resp else None)
                            st.success("Submission saved.")
                            st.rerun()

def student_grades_ui(user):
    st.header("My Grades & Feedback")
    subs = fetch_user_submissions(user["id"])
    if not subs:
        st.info("No submissions yet.")
        return
    df = pd.DataFrame([{
        "Week": r["week_number"],
        "Assignment": r["assignment_title"],
        "Submitted At (UTC)": r["submitted_at"],
        "Grade": r["grade"],
        "Feedback": r["feedback"]
    } for r in subs]).sort_values("Week")
    st.dataframe(df, use_container_width=True)

    eligible, avg = eligible_for_certificate(user["id"])
    if eligible:
        st.success(f"🎉 Eligible for Certificate. Average: {avg:.1f}")
        if st.button("Generate Certificate (PDF)"):
            cert_id = f"CA-{user['id']}-{dt.date.today().strftime('%Y%m%d')}"
            pdf = generate_certificate_pdf(user["full_name"], cert_id)
            st.download_button("Download Certificate", data=pdf, file_name=f"Certificate_{user['username']}.pdf", mime="application/pdf")
    else:
        st.warning("Not yet eligible for the certificate. Complete and pass all 6 assignments.")

def resources_ui():
    st.header("Further Study Resources")
    st.markdown("""
- **OECD AI Principles** — trustworthy AI foundations  
- **Microsoft Responsible AI Standard** — practical governance  
- **Power BI Learn** — guided analytics paths  
- **Streamlit Docs** — build data apps quickly  
- **Scikit-learn Guide** — classical ML reference  
    """)

def admin_content_ui():
    st.header("Content Management")
    mods = fetch_modules()
    mod_map = {f"Week {m['week_number']}: {m['title']}": m['id'] for m in mods}
    tab1, tab2, tab3 = st.tabs(["Add Material", "Add Assignment", "Manage Materials"])

    # ---- Add Material
    with tab1:
        sel = st.selectbox("Select Module", list(mod_map.keys()))
        m_id = mod_map[sel]
        mat_kind = st.radio("Material Type", ["Upload File", "External Link"])
        title = st.text_input("Material Title")
        if mat_kind == "Upload File":
            upl = st.file_uploader("Upload a file", type=None)
            if upl and st.button("Save Material"):
                save_path = str((UPLOADS_DIR / f"mat_m{m_id}_{upl.name}").resolve())
                with open(save_path, "wb") as f:
                    f.write(upl.getbuffer())
                add_material(m_id, title or upl.name, "file", save_path)
                st.success("Material added.")
                st.rerun()
        else:
            url = st.text_input("Paste URL")
            if st.button("Save Link"):
                if url:
                    add_material(m_id, title or url, "link", url)
                    st.success("Link added.")
                    st.rerun()

    # ---- Add Assignment (unchanged)
    with tab2:
        sel2 = st.selectbox("Select Module (for assignment)", list(mod_map.keys()), key="ass_mod")
        m_id2 = mod_map[sel2]
        a_title = st.text_input("Assignment Title", key="ass_title")
        prompt = st.text_area("Assignment Prompt", height=150)
        due = st.date_input("Due Date", value=dt.date.today()+dt.timedelta(days=7))
        if st.button("Create Assignment"):
            add_assignment(m_id2, a_title or "Assignment", prompt, str(due))
            st.success("Assignment created.")
            st.rerun()

    # ---- Manage Materials (NEW)
    with tab3:
        sel3 = st.selectbox("Select Module (to manage materials)", list(mod_map.keys()), key="manage_mod")
        m_id3 = mod_map[sel3]
        mats = fetch_materials(m_id3)
        if not mats:
            st.info("No materials yet for this module.")
        else:
            for mat in mats:
                with st.expander(f"{mat['title']}  •  ({mat['kind']})", expanded=False):
                    # Show current
                    st.write(f"**Current Title:** {mat['title']}")
                    st.write(f"**Type:** {mat['kind']}")
                    st.write(f"**Path/URL:** {mat['path_or_url']}")

                    # Edit form
                    with st.form(key=f"edit_mat_{mat['id']}"):
                        new_title = st.text_input("Title", value=mat["title"])
                        new_kind = st.selectbox("Type", ["link", "file"], index=0 if mat["kind"]=="link" else 1)
                        new_path = st.text_input("URL or File Path", value=mat["path_or_url"])
                        c1, c2, c3 = st.columns([1,1,2])
                        with c1:
                            if st.form_submit_button("Save"):
                                update_material(mat["id"], new_title, new_kind, new_path)
                                st.success("Updated.")
                                st.rerun()
                        with c2:
                            if st.form_submit_button("Delete", type="secondary"):
                                delete_material(mat["id"])
                                st.success("Deleted.")
                                st.rerun()

                    # Optional convenience: replace file by uploading a new one
                    if mat["kind"] == "file":
                        repl = st.file_uploader("Replace file (optional)", key=f"repl_{mat['id']}")
                        if repl and st.button("Upload Replacement", key=f"btn_repl_{mat['id']}"):
                            save_path = str((UPLOADS_DIR / f"mat_m{m_id3}_{repl.name}").resolve())
                            with open(save_path, "wb") as f:
                                f.write(repl.getbuffer())
                            update_material(mat["id"], mat["title"], "file", save_path)
                            st.success("File replaced.")
                            st.rerun()

def admin_gradebook_ui(user):
    st.header("Gradebook — Ungraded Submissions")
    rows = fetch_ungraded_submissions()
    if not rows:
        st.info("No ungraded submissions.")
        return
    for r in rows:
        st.markdown(f"**Week {r['week_number']} — {r['assignment_title']}**")
        st.write(f"Student: {r['student_name']} | Submitted: {r['submitted_at']}")
        if r["file_path"]:
            try:
                with open(r["file_path"], "rb") as f:
                    st.download_button("Download submission file", f.read(), file_name=os.path.basename(r["file_path"]), key=f"dl_{r['id']}")
            except Exception as e:
                st.warning(f"File unavailable: {e}")
        st.write("Text response:")
        st.code(r["text_response"] or "—", language="markdown")
        c1, c2 = st.columns([1,3])
        with c1:
            grade = st.number_input("Grade (0–100)", min_value=0.0, max_value=100.0, step=0.5, key=f"g_{r['id']}")
        with c2:
            feedback = st.text_input("Feedback", key=f"fb_{r['id']}")
        if st.button("Submit Grade", key=f"grade_{r['id']}"):
            grade_submission(r["id"], grade, feedback, user["id"])
            st.success("Graded.")
            st.rerun()

def my_account_ui(user):
    st.header("My Account")
    st.write(f"**Name:** {user['full_name']}")
    st.write(f"**Username:** {user['username']}")
    st.write(f"**Role:** {user['role']}")
    st.markdown("---")
    st.subheader("Change Password")
    with st.form("pw_form"):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Update Password")
        if submitted:
            if not new or new != confirm:
                st.error("New passwords do not match.")
            else:
                ok, msg = update_password(user["id"], current, new)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

def privacy_compliance_ui():
    st.header("Compliance & Accessibility")
    st.markdown("""
- **Privacy:** Passwords are hashed (bcrypt). Use HTTPS in production.
- **Data Retention:** Define archival policy; SQLite stored locally or on a mounted volume.
- **Accessibility:** Clear headings, descriptive links, downloadable materials, good color contrast.
- **Standards:** Transparent assessment (visible grades/feedback), micro-credential style certificate.
    """)

# ----------------------------- App -----------------------------
def main():
    run_ddl()
    ensure_seed()

    st.title(APP_TITLE)
    st.caption("Training Organizer: **Chumcred Academy**")
    if "__seed_notice__" in st.session_state:
        st.info(st.session_state.pop("__seed_notice__"))

    user = st.session_state.get("user")
    if not user:
        login_form()
        st.stop()

    with st.sidebar:
        st.markdown(f"**Signed in as:** {user['full_name']} (@{user['username']}) — *{user['role']}*")
        choice = st.radio("Navigate", [
            "My Dashboard", "Modules & Assignments", "My Grades", "My Account", "Resources", "Compliance"
        ] + (["Admin: Users", "Admin: Content", "Admin: Gradebook"] if user["role"]=="admin" else []))
        logout_button()

    if choice == "My Dashboard":
        st.subheader("Welcome")
        st.write("Use the sidebar to access modules, submit assignments, view grades, and manage your account.")
        subs = fetch_user_submissions(user["id"])
        if subs:
            df = pd.DataFrame([{
                "Week": r["week_number"],
                "Assignment": r["assignment_title"],
                "Submitted At (UTC)": r["submitted_at"],
                "Grade": r["grade"]
            } for r in subs]).sort_values("Week", ascending=False)
            st.dataframe(df, use_container_width=True, height=240)
        else:
            st.info("No submissions yet.")

    elif choice == "Modules & Assignments":
        student_modules_ui(user)

    elif choice == "My Grades":
        student_grades_ui(user)

    elif choice == "My Account":
        my_account_ui(user)

    elif choice == "Resources":
        resources_ui()

    elif choice == "Compliance":
        privacy_compliance_ui()

    elif choice == "Admin: Users":
        if user["role"]!="admin":
            st.error("Unauthorized")
        else:
            admin_create_user_ui()
            st.markdown("---")
            admin_users_table()

    elif choice == "Admin: Content":
        if user["role"]!="admin":
            st.error("Unauthorized")
        else:
            admin_content_ui()

    elif choice == "Admin: Gradebook":
        if user["role"]!="admin":
            st.error("Unauthorized")
        else:
            admin_gradebook_ui(user)

if __name__ == "__main__":
    main()
