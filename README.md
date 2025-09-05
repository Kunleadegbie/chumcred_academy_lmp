# Chumcred Academy — AI Essentials LMP (Learning Management Portal)

A production-ready Learning Management Portal built with **Python + Streamlit + SQLite**.

## Features
- Authentication with **bcrypt** (roles: admin, student)
- 6-week modules with **materials** (files/links) and **assignments**
- **Student submissions** (upload files + notes)
- **Grading workflow**; grades & feedback are visible to students
- **External resources** page
- **PDF certificate** generation (average >= 60 across all 6 assignments)
- **Change password** page for users
- Seeded **default admin** (configurable via secrets/env)

## Local Development
```bash
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=ChangeThis!123
streamlit run app.py
```

## Deployment
- Streamlit Cloud: set Secrets `ADMIN_USERNAME`, `ADMIN_PASSWORD` and deploy.
- Docker: build & run the included Dockerfile (mount a volume for persistence).
- Render/Railway/Fly.io: set start command `streamlit run app.py --server.port $PORT --server.address 0.0.0.0` and env vars.

## Persistence
- SQLite database `lmp.db` is created in the app root. Mount a volume or migrate to Postgres for scale.

## Security
- Use HTTPS, rotate credentials, and back up DB regularly.
