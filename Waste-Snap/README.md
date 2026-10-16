# WasteSnap

A community waste-reporting app built with Flask and MongoDB Atlas.

- **Citizens** report waste problems with a photo and follow their progress.
- **Admins** verify reports, assign them to workers, and resolve finished jobs.
- **Workers** start their assigned tasks and upload a photo of the fixed issue.
- **Companies** are contractors. After a complaint is resolved, a company can **request a payment** (or the admin can create one). The admin approves it and **pays it through a simulated payment gateway**, and the company watches it happen live.

```
Submitted -> Verified -> Assigned -> In Progress -> Resolved
(citizen)    (admin)     (admin)      (worker)       (admin, after the worker's photo)
```

Payments go through a **simulated gateway** (no real money moves): see "The payment demo" below.

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
  data_export.py    Keeps a copy of the database in files (see below)
  payment_gateway.py  The simulated payment gateway (methods, stages, live status)
```

## Setup (same steps on Windows and Mac)

You need **Python 3.10 or newer** and **git**.

### 1. Get the code

```
git clone <repo-url>
cd Waste-Snap
git checkout backend
cd Waste-Snap
```

The repository contains one project folder, also called `Waste-Snap`. All the commands below
(and the `.env` file) are inside that inner folder.

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

## The payment demo (simulated gateway)

A payment moves through realistic states, and every step is visible live:

```
company requests -> admin approves -> admin pays -> processing -> paid  (receipt)
                 -> admin rejects                              -> failed (retry)
```

- **Request:** on the company dashboard, a company asks to be paid for a resolved job (amount and
  note). The admin sees it under **Payments** and **Approves** (the amount can be changed) or
  **Rejects** with a reason. A rejected request can be sent again. The admin can also create a
  payment directly.
- **Checkout:** the admin clicks **Pay now** and picks **UPI**, **Bank transfer** or **Card**.
  Buttons fill in demo details, and the page lists the test values.
- **Live progress:** the payment goes through 5 steps (initiate, verify payee, authorise with the
  bank, transfer, confirm). The page updates by itself every second, with a progress bar and a
  timeline. The company can watch the same screen, and its dashboard updates on its own.
- **Failures and retry:** special test values make a payment fail on purpose. The admin sees why
  and clicks **Retry payment**. Every attempt stays in the timeline.
- **Receipt:** a printable receipt (use the browser's "Save as PDF") with the transaction ID,
  method, penalty lines and timeline.
- **Safety:** a payment cannot be paid twice (clicking twice starts only one), cannot be paid while
  a low-rating review is pending or the complaint is reopened, and a payment stuck "processing"
  (for example the server restarted) is marked failed so it can be retried.
- Card numbers, PINs and CVVs are **never saved**, only a masked label like "Visa card ending 1111".

| Method | Works | Fails on purpose |
|---|---|---|
| UPI | PIN `1234` | PIN `0000` (declined by the bank) |
| Card | `4111 1111 1111 1111` | `4000 0000 0000 0002` (insufficient funds), `...0127` (CVV check), `...0069` (expired) |
| Bank transfer | any valid account and IFSC (e.g. `HDFC0001234`) | an account number ending `0000` (account does not exist) |

For slower or faster demos set `PAYMENT_SPEED` in `.env` (1 is normal, 2 is twice as slow, 0.5 is faster).

## The database copy in files (`data/`)

MongoDB Atlas is the real database. The app also keeps a **read-only copy of the data in
ordinary files**, so it can be looked at without any database tools:

```
data/
  README.txt              what these files are
  wastesnap_backup.db     the whole database as ONE SQLite file
  json/
    users.json  complaints.json  payments.json  violations.json
```

- Open the `.json` files in any text editor, and the `.db` file with
  [DB Browser for SQLite](https://sqlitebrowser.org) (or `sqlite3 wastesnap_backup.db "SELECT * FROM complaints;"`).
- The files are rewritten when the app starts and a moment after every change. An admin can also
  open **Data** in the menu to see the files, download them, or press **Export now**.
- **Password hashes are never written to the files.** The files do contain names, emails and
  complaints, so keep the repository private if it holds real people's data.
- Switch it off with `AUTO_EXPORT=false` in `.env`. Set `DATA_EXPORT_DIR` to write somewhere else.
- This is a one-way copy: changing the files does not change the database.

## Demo script

1. Log in as the **citizen** and report an issue with a photo.
   (enter how many days the problem has existed).
2. Log in as the **admin**: Verify it, assign it to the worker (this starts the 7-day deadline).
3. Log in as the **worker**: Start work, then upload a photo and mark it done.
4. As the **admin**: Resolve it. Then open **Payments**, pick the company,
   enter an amount, and create the payment. (Or, as the **company**, request a payment for the
   resolved job and approve it as the admin.) (To show the penalty, change the
   job's `deadline` to a past date in Atlas before the worker finishes it.)
5. Log in as the **company** to see the pending payment, then as the admin
   click **Pay now**, choose a method, and watch the live payment. Try a failing test value, then
   **Retry payment**, then open the **Receipt**.
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
- Payments go through a simulated gateway (no real bank or money).
