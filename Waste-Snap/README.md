# WasteSnap

A community waste-reporting app built with Flask and MongoDB Atlas.

- **Citizens** report waste problems with a photo and follow their progress.
- **Admins** verify reports, assign them to workers, and resolve finished jobs.
- **Workers** start their assigned tasks and upload a photo of the fixed issue.
- **Companies** are contractors: the admin creates a payment for a company after a complaint is resolved, and the company sees its payments.

```
Submitted -> Verified -> Assigned -> In Progress -> Resolved
(citizen)    (admin)     (admin)      (worker)       (admin, after the worker's photo)
```

Payments are records only (pending -> paid). No real money moves.

**Rules added on top of the workflow**

- **Days existing (citizen):** when reporting, the citizen enters how many days the
  problem has already existed. The page shows "Existing for N days", and N goes up by
  one every day until the complaint is resolved.
- **Ratings (citizen):** once a complaint is resolved, the citizen can give a 1-5 star
  rating and an optional comment, once. The admin and the worker can see it.
- **Low-rating penalty (admin has the final say):** a 1 or 2 star rating does **not** cut any
  pay by itself. It opens a review on the admin's **Reviews** page, where the admin sees the
  comment, whether the worker finished on time, and the photos. **Approve** takes Rs. 25 off
  the job's payment; **Dismiss** leaves it unchanged. A payment cannot be marked as paid while
  its review is waiting.
- **Worker deadline:** a worker has **7 days** after a complaint is assigned to finish it.
  The dashboards show days left, or **Overdue**.
- **Late penalty:** a job finished after the deadline costs **Rs. 50**, which is taken off
  the payment for that job (the admin sees it when creating the payment, and the
  company sees the deduction). The numbers are `DEADLINE_DAYS` and `LATE_PENALTY` at the
  top of `backend/db_helpers.py`.
- **Not started in time:** a job still "Assigned" 48 hours after assignment shows a warning
  to the worker and the admin. No money is taken.
- **Duplicate proof photo:** a worker's "fixed" photo is refused if it is the citizen's own
  photo, was used as proof for another job, or is an old rejected proof. The attempt is
  recorded in the violation log.
- **Invalid or fake complaint:** the admin can **Reject** a new or verified complaint as
  *invalid* (the citizen gets a strike) or *duplicate* (no strike). 3 strikes within 90 days
  pause the citizen's reporting.
- **Duplicate report:** the same type and location reported again within 7 days is refused
  for the same citizen (with a link to the earlier report). If another citizen reported it,
  the new complaint is saved but flagged for the admin.
- **Daily limit:** a citizen can send 5 reports per day.
- **Reopen:** within 3 days of resolution, and before rating, the citizen can say "it is not
  fixed". The complaint goes back to the same worker with a new 3-day deadline, the payment is
  put on hold, and the reopen is recorded against the worker. Once per complaint, and not after
  the payment is paid.
- **Reject the worker's work (admin):** when a worker marks a job as done, the admin can
  **Resolve** it or **Reject work** with a reason. A rejected job goes back to the same worker
  with a new 3-day deadline, the rejected photo can never be uploaded again, and the rejection
  is recorded against the worker. A job that was already late stays late, so the Rs. 50 penalty
  is not erased by a redo.
- **Admin response time:** a complaint left in "Submitted" for more than 48 hours turns red on
  the admin page. It is an alert only (no penalty).

All these numbers are constants at the top of `backend/db_helpers.py`. The admin's
**Reviews** page also shows the violation log.

## Project layout

```
backend/
  app.py            Flask app, home page, role redirect
  config.py         Reads settings from .env
  models.py         MongoDB connection + User class
  db_helpers.py     All database reads and writes
  routes/           auth, complaints, admin, workers, company
  templates/        HTML pages (base.html is the shared layout)
  static/css|js     Styles and scripts
  static/uploads/   Uploaded photos (not committed)
  init_db.py        Creates database indexes (run once)
  create_admin.py / create_worker.py / create_company.py   Make accounts
  seed_demo.py      Demo accounts + sample complaints
```

## Setup (same steps on Windows and Mac)

You need **Python 3.10 or newer** and **git**.

### 1. Get the code

```
git clone <repo-url>
cd Waste-Snap
```

### 2. Create a virtual environment and install packages

**Mac / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

**Windows (PowerShell)**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

If PowerShell blocks the activate script, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.

### 3. Add your settings

Copy `.env.example` to `.env` (in the project root, next to this README):

```
cp .env.example .env          # Mac / Linux
copy .env.example .env        # Windows
```

Then edit `.env`:

- `SECRET_KEY` - any long random text. Generate one with
  `python -c "import secrets; print(secrets.token_hex(32))"`
- `MONGODB_URI` - the Atlas connection string. Ask your teammate for it
  (never commit it or paste it in chat). Each laptop's IP must be allowed
  under **Network Access** in MongoDB Atlas.
- `MONGODB_DATABASE` - the database name. Everyone on the team must use
  the same one to share data.

### 4. Prepare the database (once per database)

```
cd backend
python init_db.py
python seed_demo.py
```

`seed_demo.py` creates one account for every role and three sample
complaints. Log in with these (password for all: `Demo@1234`):

| Role | Email |
|---|---|
| Admin | admin@wastesnap.test |
| Worker | worker@wastesnap.test |
| Company | company@wastesnap.test |
| Citizen | citizen@wastesnap.test |

Use `python create_admin.py`, `create_worker.py` or `create_company.py`
to make real accounts instead. Citizens sign up on the website.

### 5. Run

```
python app.py
```

Open <http://127.0.0.1:5000/>.

## Demo script

1. Log in as the **citizen** and report an issue with a photo.
   (enter how many days the problem has existed).
2. Log in as the **admin**: Verify it, assign it to the worker (this starts the 7-day deadline).
3. Log in as the **worker**: Start work, then upload a photo and mark it done.
4. As the **admin**: Resolve it. Then open **Payments**, pick the company,
   enter an amount, and create the payment. (To show the penalty, change the
   job's `deadline` to a past date in Atlas before the worker finishes it.)
5. Log in as the **company** to see the pending payment, then as the admin
   mark it as paid.
6. Log in as the **citizen** again and rate the resolved complaint. Try 1 star, then, as the
   admin, open **Reviews** and approve or dismiss the penalty.
7. To see the other rules: report the same place twice (duplicate), reject a complaint as
   invalid three times (strikes), reopen a resolved complaint, or have the worker upload the
   citizen's own photo as proof (refused).

(Use a private/incognito window per role, or log out between steps.)

## Working together

- Never commit `.env` or uploaded photos - both are in `.gitignore`.
- Photos live in `backend/static/uploads/` on each computer, so a photo
  uploaded on one laptop is not visible on another. The database records
  are shared, the image files are not. For a demo, run the whole flow on
  one machine.
- Pull before you start and push when you finish, to avoid merge conflicts.

## Known limitations (it is a demo)

- No password reset or email verification.
- No CSRF protection on the forms.
- Uploaded photos are served from the static folder.
- Payments are simulated.
