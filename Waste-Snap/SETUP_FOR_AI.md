# WasteSnap - setup instructions for an AI coding assistant

Paste this file (or point your assistant at it) on a new laptop, Mac or
Windows. It tells the assistant how to get the project running.

You are helping a student set up a college demo project on their laptop.
Do the steps in order, run the commands yourself where you can, and stop to
ask the user only where a step says **ASK**.

## About the project

WasteSnap is a Flask web app that stores data in MongoDB Atlas (cloud).

- Roles: citizen, worker, admin, company.
- Backend code is in `backend/`. Run everything from there.
- Templates are in `backend/templates/`, static files in `backend/static/`.
- Settings come from a `.env` file in the project root (next to this file).
- Python 3.10 or newer is required.

## Rules

- **Never print, log, commit or paste the contents of `.env`.** It holds the
  database password.
- **Never put the MongoDB URI in any file except `.env`.**
- Do **not** modify application code to get past a setup problem. Fix the
  environment instead. If code really looks broken, report it to the user.
- Do not run `seed_demo.py` unless the user confirms the database is empty
  (step 6).
- Work on the `backend` git branch.

## Step 1 - Check prerequisites

Run these and confirm each prints a version:

| Check | Mac | Windows |
|---|---|---|
| Python | `python3 --version` | `py --version` |
| Git | `git --version` | `git --version` |

If Python is older than 3.10 or missing, tell the user to install the latest
Python from https://www.python.org/downloads/ (on Windows tick
"Add python.exe to PATH") and then continue.

## Step 2 - Get the code on the right branch

If the project folder does not exist yet:

```
git clone https://github.com/Mohith-Prasanna-07/Waste-Snap
cd Waste-Snap
```

Then, in the project folder:

```
git checkout backend
git pull
```

Check: the folder `backend/routes/` must exist and contain `company.py`. If
not, the wrong branch is checked out.

## Step 3 - Create the virtual environment and install packages

**Mac**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

**Windows - PowerShell**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

- If PowerShell refuses to run the activate script, run
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.
- **Windows - Command Prompt (cmd)** uses `.venv\Scripts\activate.bat`
  instead. A `.ps1` script does nothing in `cmd`.
- The prompt should start with `(.venv)` once the environment is active. If
  it does not, the environment is not active.

Check: `pip list` should include Flask, Flask-Login, pymongo and python-dotenv.

## Step 4 - Create the `.env` file

Copy the template (project root):

```
cp .env.example .env          # Mac
copy .env.example .env        # Windows
```

**ASK** the user for these values and write them into `.env`. Do not echo
them back afterwards.

| Key | Value |
|---|---|
| `SECRET_KEY` | Generate it yourself: `python3 -c "import secrets; print(secrets.token_hex(32))"` (Windows: `python`). Each laptop can have its own. |
| `MONGODB_URI` | The user's Atlas connection string, from their teammate or their own `.env` on another laptop. It starts with `mongodb+srv://`. **ASK** the user to paste it directly into `.env` themselves if they prefer not to share it with you. |
| `MONGODB_DATABASE` | **ASK**. It must be the **same name** the team already uses (for example `wastesnap_test`). A different name creates a separate empty database. |
| `FLASK_DEBUG` | `true` for development. |

## Step 5 - Let this laptop connect to Atlas

Atlas blocks unknown IP addresses. Tell the user to do this in the browser:

1. Go to https://cloud.mongodb.com and open the project.
2. **Security -> Network Access -> Add IP Address -> Add Current IP Address**
   (or `0.0.0.0/0` temporarily for a demo, and remove it afterwards).

The IP changes on a new network (home, campus, VPN), so this may need
repeating.

## Step 6 - Prepare the database (only if needed)

Run from the `backend` folder:

```
cd backend
python3 init_db.py        # Windows: python init_db.py
```

Expected output: `WASTE SNAP database indexes created!`. This is safe to
repeat.

- A timeout after about 5 seconds means Atlas is not reachable: re-check
  step 5, and check the connection string.
- An authentication error means the username or password in the connection
  string is wrong.

**ASK:** "Is this database already seeded with demo data by another laptop?"

- **Yes (usual case):** skip seeding.
- **No, it is empty:** run `python3 seed_demo.py` (Windows: `python seed_demo.py`).
  It creates one account per role and three sample complaints.

## Step 7 - Run the app

From the `backend` folder, with the virtual environment active:

```
python3 app.py            # Windows: python app.py
```

Open http://127.0.0.1:5000/ . The green landing page should load.

Stop the server with `Ctrl+C`. On Windows with newer Python versions, a
harmless `OSError: [WinError 10038]` traceback may print while it stops.
Ignore it.

## Step 8 - Verify it works

Demo logins (password for all is `Demo@1234`), only if the database was
seeded:

| Role | Email |
|---|---|
| Admin | admin@wastesnap.test |
| Worker | worker@wastesnap.test |
| Company | company@wastesnap.test |
| Citizen | citizen@wastesnap.test |

Quick check: log in as the admin. The Complaints page should list the
complaints. Visiting `/admin` while logged in as the citizen should show
403 Forbidden.

Workflow to try: citizen reports an issue with a photo -> admin Verify ->
admin assigns the worker -> worker Start work -> worker uploads a photo and
marks it done -> admin Resolve -> admin Payments: create a payment for the
company -> company sees it as pending -> admin marks it as paid.

## Known behaviour (not bugs)

- **Photos do not sync between laptops.** Uploads are saved in
  `backend/static/uploads/` on each computer; only the filename goes into
  the shared database. A photo uploaded on one laptop will show as a
  missing image on another.
- Passwords must be at least 8 characters.
- Payments are demo records only. No real money moves.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `MONGODB_URI is missing` | `.env` is missing or is not in the project root next to `README.md`. |
| Timeout on `init_db.py` or login | IP not allowed in Atlas (step 5), or wrong connection string. |
| `ModuleNotFoundError` | The virtual environment is not active or packages are not installed (step 3). |
| `python` not found on Mac | Use `python3`. |
| `.\.venv\Scripts\Activate.ps1` does nothing | The shell is `cmd`, not PowerShell. Use `activate.bat`. |
| Login says "Invalid email or password" | Wrong database name in `.env`, or the database was never seeded. |
| Port 5000 already in use (Mac) | AirPlay Receiver uses it. Turn it off in System Settings -> General -> AirDrop & Handoff, or change the port in `app.py`. |

## Committing changes

Do not commit `.env`, `.venv/` or uploaded photos (they are gitignored). Pull
before starting work and push when finished:

```
git pull
git add -A
git commit -m "Describe the change"
git push origin backend
```
