
import secrets
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash

from models import User, get_db, to_object_id


# -----------------------------------------
# RULES
# -----------------------------------------

# A worker gets this many days to finish a job after it is assigned
DEADLINE_DAYS = 7

# Rupees taken off the payment when a job is finished after the deadline
LATE_PENALTY = 50

# A rating of this many stars or fewer opens a penalty review.
# The admin decides whether the rupees are really taken off.
LOW_RATING_MAX = 2
RATING_PENALTY = 25

# Warnings (no money): hours before the admin / worker should have acted
RESPONSE_WARNING_HOURS = 48     # admin has not verified a new complaint
START_WARNING_HOURS = 48        # worker has not started an assigned job

# Citizen limits
MAX_REPORTS_PER_DAY = 5         # reports a citizen can send per day
DUPLICATE_DAYS = 7              # "same problem" look-back window
STRIKE_LIMIT = 3                # invalid complaints before reporting is paused
STRIKE_DAYS = 90                # strikes older than this are forgotten

# Reopening a resolved complaint
REOPEN_WINDOW_DAYS = 3          # how long after resolving the citizen can reopen
REOPEN_DEADLINE_DAYS = 3        # new deadline for the worker after a reopen

# When the admin rejects a worker's finished job, the worker gets this
# many days to do it again
REJECT_DEADLINE_DAYS = 3


# -----------------------------------------
# SMALL CONVERTERS
# -----------------------------------------

# Turn a MongoDB complaint document into a dictionary
# that the HTML templates can use (complaint.id, complaint.status ...)
def complaint_to_dict(document):

    complaint = dict(document)

    complaint["id"] = str(complaint.pop("_id"))

    now = datetime.now()

    # How many days the problem has existed:
    # the days the citizen entered + the days since it was reported.
    # It is worked out every time the page loads, so it goes up by
    # one each day, and it stops counting once the complaint is resolved.
    end_time = now

    if complaint.get("status") == "Resolved":
        end_time = (
            complaint.get("resolved_at")
            or complaint.get("updated_at")
            or now
        )

    if complaint.get("status") == "Rejected":
        end_time = (
            complaint.get("rejected_at")
            or complaint.get("updated_at")
            or now
        )

    days_since_report = (
        end_time.date() - complaint["created_at"].date()
    ).days

    complaint["existing_days"] = (
        (complaint.get("days_existing") or 0)
        + max(days_since_report, 0)
    )

    # Worker deadline: days left, and whether it is overdue
    deadline = complaint.get("deadline")

    complaint["days_left"] = None
    complaint["is_overdue"] = False

    if (
        deadline
        and complaint.get("status") in ("Assigned", "In Progress")
        and not complaint.get("worker_done")
    ):
        complaint["days_left"] = (deadline.date() - now.date()).days
        complaint["is_overdue"] = now > deadline

    # Admin alert: a new complaint nobody has verified for too long
    complaint["waiting_days"] = (now - complaint["created_at"]).days
    complaint["needs_attention"] = (
        complaint.get("status") == "Submitted"
        and now - complaint["created_at"]
        > timedelta(hours=RESPONSE_WARNING_HOURS)
    )

    # Worker warning: assigned but not started for too long
    assigned_at = complaint.get("assigned_at")

    complaint["start_overdue"] = bool(
        complaint.get("status") == "Assigned"
        and assigned_at
        and now - assigned_at > timedelta(hours=START_WARNING_HOURS)
    )

    # Citizen can reopen a resolved complaint for a few days, once,
    # and only before rating it
    resolved_at = (
        complaint.get("resolved_at")
        or complaint.get("updated_at")
        or now
    )

    complaint["can_reopen"] = bool(
        complaint.get("status") == "Resolved"
        and not complaint.get("feedback_rating")
        and not complaint.get("reopened")
        and now - resolved_at <= timedelta(days=REOPEN_WINDOW_DAYS)
    )

    return complaint


# Find a user using their email address
def get_user_by_email(email):

    document = get_db().users.find_one({"email": email})

    return User(document) if document else None


# Create an account with the given role
def create_user(name, email, password, role):

    document = {
        "name": name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "role": role,
        "created_at": datetime.now()
    }

    result = get_db().users.insert_one(document)

    document["_id"] = result.inserted_id

    return User(document)


# Create a new citizen account
def create_citizen(name, email, password):

    return create_user(name, email, password, "citizen")


# Find a user using their ID
def get_user_by_id(user_id):

    # Make sure the ID is valid
    object_id = to_object_id(user_id)

    if object_id is None:
        return None

    document = get_db().users.find_one({"_id": object_id})

    return User(document) if document else None


# Lower-case a location and squash spaces: "  Main  ST " -> "main st"
def normalize_location(text):

    return " ".join(str(text).lower().split())


# Save a new citizen complaint
def create_complaint(user_id, issue_type, description,
                     location, image_filename, days_existing=0,
                     image_hash=None, possible_duplicate_of=None):

    now = datetime.now()

    document = {
        "user_id": to_object_id(user_id),
        "type": issue_type,
        "description": description,
        "location": location,

        # Lower-case version of the location, used to spot duplicates
        "location_key": normalize_location(location),

        "image_filename": image_filename,

        # Fingerprint of the photo (to stop a worker re-using it as proof)
        "image_hash": image_hash,

        # Set when someone else reported the same problem recently
        "possible_duplicate_of": possible_duplicate_of,

        # Days the problem had existed when the citizen reported it
        "days_existing": days_existing,

        "status": "Submitted",
        "worker_done": False,
        "resolution_image_filename": None,
        "assigned_worker_id": None,

        # Worker deadline (set when the complaint is assigned)
        "assigned_at": None,
        "deadline": None,
        "worker_done_at": None,
        "was_late": False,
        "resolved_at": None,

        "resolution_image_hash": None,
        "old_proof_hashes": [],

        # Citizen feedback (given after the complaint is resolved)
        "feedback_rating": None,
        "feedback_comment": "",
        "feedback_at": None,

        # Low rating penalty: None / "pending" / "approved" / "dismissed"
        "rating_penalty": None,

        # Reopened by the citizen ("it is not fixed")
        "reopened": False,

        # Rejected by the admin (invalid or duplicate)
        "rejected_reason": None,
        "rejected_note": "",
        "rejected_at": None,

        "created_at": now,
        "updated_at": now
    }

    result = get_db().complaints.insert_one(document)

    document["_id"] = result.inserted_id

    return complaint_to_dict(document)


# -----------------------------------------
# GET COMPLAINTS SUBMITTED BY A CITIZEN
# -----------------------------------------

def get_complaints_by_user(user_id):

    # Show newest complaints first
    records = get_db().complaints.find(
        {"user_id": to_object_id(user_id)}
    ).sort("created_at", -1)

    return [complaint_to_dict(record) for record in records]


# -----------------------------------------
# GET ALL COMPLAINTS FOR ADMIN
# -----------------------------------------

def get_all_complaints():

    records = list(
        get_db().complaints.find().sort("created_at", -1)
    )

    # Look up every citizen and worker in one query
    user_ids = set()

    for record in records:
        user_ids.add(record["user_id"])

        if record.get("assigned_worker_id"):
            user_ids.add(record["assigned_worker_id"])

    users = {
        user["_id"]: user
        for user in get_db().users.find(
            {"_id": {"$in": list(user_ids)}}
        )
    }

    # Return (complaint, citizen) pairs for the admin page
    pairs = []

    for record in records:

        citizen = users.get(record["user_id"])
        worker = users.get(record.get("assigned_worker_id"))

        complaint = complaint_to_dict(record)

        complaint["worker_name"] = (
            worker["name"] if worker else None
        )

        pairs.append((
            complaint,
            User(citizen) if citizen else {"name": "Unknown user"}
        ))

    return pairs



# -----------------------------------------
# CHANGE A COMPLAINT'S STATUS
# -----------------------------------------

# The filter checks the current status and the update changes it
# in a single step, so a complaint cannot skip a stage.
def _move_complaint(filters, changes):

    changes["updated_at"] = datetime.now()

    result = get_db().complaints.update_one(
        filters,
        {"$set": changes}
    )

    return result.modified_count == 1


# -----------------------------------------
# VERIFY A COMPLAINT
# -----------------------------------------

def verify_complaint(complaint_id):

    object_id = to_object_id(complaint_id)

    if object_id is None:
        return False

    # Only submitted complaints can be verified
    return _move_complaint(
        {"_id": object_id, "status": "Submitted"},
        {"status": "Verified"}
    )


# -----------------------------------------
# GET ALL WORKERS
# -----------------------------------------

def get_workers():

    records = get_db().users.find(
        {"role": "worker"}
    ).sort("name", 1)

    return [User(record) for record in records]


# -----------------------------------------
# ASSIGN COMPLAINT TO WORKER
# -----------------------------------------

def assign_complaint(complaint_id, worker_id):

    object_id = to_object_id(complaint_id)
    worker_object_id = to_object_id(worker_id)

    # Check the complaint and worker IDs are valid
    if object_id is None or worker_object_id is None:
        return False

    # Ensure the selected user is actually a worker
    worker = get_db().users.find_one(
        {"_id": worker_object_id, "role": "worker"}
    )

    if worker is None:
        return False

    # Only verified complaints can be assigned
    return _move_complaint(
        {"_id": object_id, "status": "Verified"},
        {"assigned_worker_id": worker_object_id,
         "status": "Assigned",
         "assigned_at": datetime.now(),
         "deadline": datetime.now() + timedelta(days=DEADLINE_DAYS),
         "was_late": False}
    )


# -----------------------------------------
# GET COMPLAINTS ASSIGNED TO A WORKER
# -----------------------------------------

def get_worker_complaints(worker_id):

    records = get_db().complaints.find(
        {"assigned_worker_id": to_object_id(worker_id)}
    ).sort("created_at", -1)

    return [complaint_to_dict(record) for record in records]


# -----------------------------------------
# WORKER STARTS WORK ON A COMPLAINT
# -----------------------------------------

def start_work_on_complaint(complaint_id, worker_id):

    object_id = to_object_id(complaint_id)
    worker_object_id = to_object_id(worker_id)

    if object_id is None or worker_object_id is None:
        return False

    # Must belong to this worker and be Assigned
    return _move_complaint(
        {"_id": object_id,
         "assigned_worker_id": worker_object_id,
         "status": "Assigned"},
        {"status": "In Progress"}
    )


# -----------------------------------------
# WORKER MARKS COMPLAINT AS DONE
# -----------------------------------------

def mark_work_done(complaint_id, worker_id, photo_filename,
                   photo_hash=None):

    object_id = to_object_id(complaint_id)
    worker_object_id = to_object_id(worker_id)

    if object_id is None or worker_object_id is None:
        return False

    # Photograph must be provided
    if not photo_filename:
        return False

    # Must belong to this worker, be In Progress,
    # and not already be marked as done
    filters = {
        "_id": object_id,
        "assigned_worker_id": worker_object_id,
        "status": "In Progress",
        "worker_done": False
    }

    complaint = get_db().complaints.find_one(filters)

    if complaint is None:
        return False

    # Finishing after the deadline is late (the payment is reduced later)
    now = datetime.now()
    deadline = complaint.get("deadline")

    return _move_complaint(
        filters,
        {"resolution_image_filename": photo_filename,
         "resolution_image_hash": photo_hash,
         "worker_done": True,
         "worker_done_at": now,
         "was_late": bool(
             complaint.get("was_late") or (deadline and now > deadline)
         )}
    )


# -----------------------------------------
# ADMIN RESOLVES A COMPLETED COMPLAINT
# -----------------------------------------

def resolve_complaint(complaint_id):

    object_id = to_object_id(complaint_id)

    if object_id is None:
        return False

    # Must be In Progress, finished by the worker,
    # and have completion evidence
    resolved = _move_complaint(
        {"_id": object_id,
         "status": "In Progress",
         "worker_done": True,
         "resolution_image_filename": {"$nin": [None, ""]}},
        {"status": "Resolved", "resolved_at": datetime.now()}
    )

    # A payment that was put on hold by a reopen can go ahead again
    if resolved:
        get_db().payments.update_many(
            {"complaint_id": object_id, "status": "on_hold"},
            {"$set": {"status": "pending"}}
        )

    return resolved


# -----------------------------------------
# ADMIN REJECTS A WORKER'S FINISHED WORK ("it is not really done")
# -----------------------------------------
#
# The job goes back to the same worker, who must do it again and upload
# a new photo. It counts against the worker (violation log).
# Returns (True/False, message for the admin)

def reject_work(complaint_id, reason):

    object_id = to_object_id(complaint_id)

    reason = str(reason).strip()[:300]

    if object_id is None:
        return False, "Complaint not found."

    if not reason:
        return False, "Please say what is wrong with the work."

    complaint = get_db().complaints.find_one(
        {"_id": object_id, "status": "In Progress", "worker_done": True}
    )

    if complaint is None:
        return False, "Only work that the worker marked as done can be rejected."

    now = datetime.now()

    rejected = _move_complaint(
        {"_id": object_id, "status": "In Progress", "worker_done": True},
        {"worker_done": False,
         "worker_done_at": None,
         "work_rejected_reason": reason,
         "work_rejected_at": now,
         "rejected_work_image": complaint.get("resolution_image_filename"),
         "resolution_image_filename": None,
         "resolution_image_hash": None,
         # a fresh deadline to do it again (was_late is kept as it was)
         "deadline": now + timedelta(days=REJECT_DEADLINE_DAYS)}
    )

    if not rejected:
        return False, "This work could not be rejected."

    # Remember the rejected photo so it cannot be uploaded again,
    # and count how many times the work was rejected
    changes = {"$inc": {"work_rejected_count": 1}}

    if complaint.get("resolution_image_hash"):
        changes["$push"] = {
            "old_proof_hashes": complaint["resolution_image_hash"]
        }

    get_db().complaints.update_one({"_id": object_id}, changes)

    # It counts against the worker
    if complaint.get("assigned_worker_id"):
        log_violation(
            complaint["assigned_worker_id"], "work_rejected", object_id,
            reason
        )

    return True, (
        "Work rejected. The job went back to the worker, who has "
        f"{REJECT_DEADLINE_DAYS} days to do it again."
    )


# -----------------------------------------
# CITIZEN GIVES A RATING AND FEEDBACK
# -----------------------------------------

def add_feedback(complaint_id, user_id, rating, comment):

    object_id = to_object_id(complaint_id)
    user_object_id = to_object_id(user_id)

    if object_id is None or user_object_id is None:
        return False

    # The rating is a whole number from 1 to 5
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        return False

    changes = {
        "feedback_rating": rating,
        "feedback_comment": comment.strip()[:500],
        "feedback_at": datetime.now()
    }

    # A low rating does NOT cut any payment by itself.
    # It goes to the admin, who decides if the reason is valid.
    if rating <= LOW_RATING_MAX:
        changes["rating_penalty"] = "pending"

    # Only the citizen who reported it, only once it is resolved,
    # and only if no rating has been given yet
    result = get_db().complaints.update_one(
        {"_id": object_id,
         "user_id": user_object_id,
         "status": "Resolved",
         "feedback_rating": None},
        {"$set": changes}
    )

    return result.modified_count == 1


# -----------------------------------------
# SUMMARY FOR A WORKER DASHBOARD
# -----------------------------------------

def worker_summary(complaints):

    late_jobs = [
        c for c in complaints
        if c.get("worker_done") and c.get("was_late")
    ]

    ratings = [
        c["feedback_rating"] for c in complaints
        if c.get("feedback_rating")
    ]

    approved_ratings = [
        c for c in complaints if c.get("rating_penalty") == "approved"
    ]

    return {
        "open_jobs": len([
            c for c in complaints if c["status"] != "Resolved"
        ]),
        "overdue_jobs": len([
            c for c in complaints if c["is_overdue"]
        ]),
        "start_warnings": len([
            c for c in complaints if c["start_overdue"]
        ]),
        "rejected_jobs": len([
            c for c in complaints if c.get("work_rejected_count")
        ]),
        "reopened_jobs": len([
            c for c in complaints if c.get("reopened")
        ]),
        "reviews_pending": len([
            c for c in complaints if c.get("rating_penalty") == "pending"
        ]),
        "late_jobs": len(late_jobs),
        "penalty_total": (
            len(late_jobs) * LATE_PENALTY
            + len(approved_ratings) * RATING_PENALTY
        ),
        "average_rating": (
            round(sum(ratings) / len(ratings), 1) if ratings else None
        ),
        "rating_count": len(ratings)
    }


# -----------------------------------------
# GET RESOLVED COMPLAINTS FOR A CITIZEN
# -----------------------------------------

def get_resolved_complaints_by_user(user_id):

    # Show the five most recently updated complaints
    records = get_db().complaints.find(
        {"user_id": to_object_id(user_id),
         "status": "Resolved"}
    ).sort("updated_at", -1).limit(5)

    return [complaint_to_dict(record) for record in records]



# =========================================================
# COMPANIES AND PAYMENTS
# =========================================================
#
# Admin pays a company for work on a Resolved complaint.
# Payment status flow:  pending -> paid
# (Payments are only records in this demo - no real money moves.)

# -----------------------------------------
# GET ALL COMPANIES
# -----------------------------------------

def get_companies():

    records = get_db().users.find(
        {"role": "company"}
    ).sort("name", 1)

    return [User(record) for record in records]


# -----------------------------------------
# GET RESOLVED COMPLAINTS THAT HAVE NO PAYMENT YET
# -----------------------------------------

def get_resolved_without_payment():

    paid_ids = get_db().payments.distinct("complaint_id")

    records = get_db().complaints.find(
        {"status": "Resolved", "_id": {"$nin": paid_ids}}
    ).sort("updated_at", -1)

    return [complaint_to_dict(record) for record in records]


# -----------------------------------------
# CREATE A PAYMENT FOR A RESOLVED COMPLAINT
# -----------------------------------------

def create_payment(complaint_id, company_id, amount_text):

    complaint_object_id = to_object_id(complaint_id)
    company_object_id = to_object_id(company_id)

    if complaint_object_id is None or company_object_id is None:
        return False

    # Read the amount as money (two decimal places)
    try:
        amount = Decimal(str(amount_text).strip())

    except InvalidOperation:
        return False

    if not amount.is_finite() or amount <= 0 or amount > 1000000:
        return False

    amount = float(round(amount, 2))

    # The complaint must be resolved
    complaint = get_db().complaints.find_one(
        {"_id": complaint_object_id, "status": "Resolved"}
    )

    if complaint is None:
        return False

    # The selected user must be a company
    company = get_db().users.find_one(
        {"_id": company_object_id, "role": "company"}
    )

    if company is None:
        return False

    # A late job has LATE_PENALTY taken off the payment.
    # A low rating costs RATING_PENALTY only if the admin approved it.
    penalty_late = LATE_PENALTY if complaint.get("was_late") else 0

    penalty_rating = (
        RATING_PENALTY
        if complaint.get("rating_penalty") == "approved" else 0
    )

    penalty = penalty_late + penalty_rating

    if amount <= penalty:
        return False

    document = {
        "complaint_id": complaint_object_id,
        "company_id": company_object_id,
        "worker_id": complaint.get("assigned_worker_id"),
        "amount": amount,
        "penalty": penalty,
        "penalty_late": penalty_late,
        "penalty_rating": penalty_rating,
        "net_amount": round(amount - penalty, 2),
        "status": "pending",
        "reference": (
            "PAY-"
            + datetime.now().strftime("%Y%m%d")
            + "-"
            + secrets.token_hex(2).upper()
        ),
        "note": "",
        "created_at": datetime.now(),
        "paid_at": None
    }

    # payments.complaint_id is unique (see init_db.py),
    # so one complaint can only be paid once
    try:
        get_db().payments.insert_one(document)

    except DuplicateKeyError:
        return False

    return True


# -----------------------------------------
# ADMIN MARKS A PAYMENT AS PAID
# -----------------------------------------

def mark_payment_paid(payment_id):

    object_id = to_object_id(payment_id)

    if object_id is None:
        return False

    # Do not pay while a low-rating review is still waiting for the admin
    payment = get_db().payments.find_one({"_id": object_id})

    if payment is not None:

        complaint = get_db().complaints.find_one(
            {"_id": payment["complaint_id"]}
        )

        if complaint and complaint.get("rating_penalty") == "pending":
            return False

    result = get_db().payments.update_one(
        {"_id": object_id, "status": "pending"},
        {"$set": {"status": "paid", "paid_at": datetime.now()}}
    )

    return result.modified_count == 1


# -----------------------------------------
# GET PAYMENTS (all, or for one company)
# -----------------------------------------

def get_payments(company_id=None):

    filters = {}

    if company_id is not None:
        filters["company_id"] = to_object_id(company_id)

    records = list(
        get_db().payments.find(filters).sort("created_at", -1)
    )

    # Look up the related complaints and companies
    complaints = {
        complaint["_id"]: complaint
        for complaint in get_db().complaints.find(
            {"_id": {"$in": [r["complaint_id"] for r in records]}}
        )
    }

    companies = {
        company["_id"]: company
        for company in get_db().users.find(
            {"_id": {"$in": [r["company_id"] for r in records]}}
        )
    }

    payments = []

    for record in records:

        payment = dict(record)

        payment["id"] = str(payment.pop("_id"))

        # Payments made before penalties existed have no penalty
        payment.setdefault("penalty", 0)
        payment.setdefault("net_amount", payment["amount"])

        complaint = complaints.get(record["complaint_id"], {})
        company = companies.get(record["company_id"], {})

        payment["complaint_ref"] = str(record["complaint_id"])[-6:]
        payment["complaint_type"] = complaint.get("type", "")
        payment["complaint_location"] = complaint.get("location", "")
        payment["rating"] = complaint.get("feedback_rating")
        payment["rating_review"] = complaint.get("rating_penalty")
        payment["company_name"] = company.get("name", "Unknown")

        payments.append(payment)

    return payments



# =========================================================
# RULES, VIOLATIONS AND REVIEWS
# =========================================================

# -----------------------------------------
# VIOLATION LOG (strikes and warnings kept for the admin)
# -----------------------------------------
#
# kinds: invalid_complaint (citizen), duplicate_photo (worker),
#        reopened (worker), low_rating_penalty (worker)

def log_violation(user_id, kind, complaint_id=None, note=""):

    get_db().violations.insert_one({
        "user_id": to_object_id(user_id),
        "kind": kind,
        "complaint_id": (
            to_object_id(complaint_id) if complaint_id else None
        ),
        "note": str(note)[:300],
        "created_at": datetime.now()
    })


# Latest violations with the people's names (admin page)
def get_violations(limit=50):

    records = list(
        get_db().violations.find().sort("created_at", -1).limit(limit)
    )

    users = {
        user["_id"]: user
        for user in get_db().users.find(
            {"_id": {"$in": [r["user_id"] for r in records]}}
        )
    }

    violations = []

    for record in records:

        violation = dict(record)

        violation["id"] = str(violation.pop("_id"))

        user = users.get(record["user_id"], {})

        violation["user_name"] = user.get("name", "Unknown")
        violation["user_role"] = user.get("role", "")

        violation["complaint_ref"] = (
            str(record["complaint_id"])[-6:]
            if record.get("complaint_id") else ""
        )

        violations.append(violation)

    return violations


# Number of violations of one kind for a user
def count_violations(user_id, kind):

    return get_db().violations.count_documents(
        {"user_id": to_object_id(user_id), "kind": kind}
    )


# -----------------------------------------
# CITIZEN LIMITS: daily limit, strikes, duplicates
# -----------------------------------------

def count_reports_today(user_id):

    midnight = datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    return get_db().complaints.count_documents(
        {"user_id": to_object_id(user_id),
         "created_at": {"$gte": midnight}}
    )


# Invalid-complaint strikes in the last STRIKE_DAYS days
def count_strikes(user_id):

    since = datetime.now() - timedelta(days=STRIKE_DAYS)

    return get_db().violations.count_documents(
        {"user_id": to_object_id(user_id),
         "kind": "invalid_complaint",
         "created_at": {"$gte": since}}
    )


# Look for the same problem (same type and place) reported recently.
# Returns (id of this citizen's own open report or None,
#          id of someone else's open report or None)
def find_duplicates(user_id, issue_type, location):

    user_object_id = to_object_id(user_id)

    since = datetime.now() - timedelta(days=DUPLICATE_DAYS)

    records = list(
        get_db().complaints.find({
            "type": issue_type,
            "location_key": normalize_location(location),
            "created_at": {"$gte": since},
            "status": {"$in": ["Submitted", "Verified",
                               "Assigned", "In Progress"]}
        }).sort("created_at", -1)
    )

    own = next(
        (r for r in records if r["user_id"] == user_object_id), None
    )

    other = next(
        (r for r in records if r["user_id"] != user_object_id), None
    )

    return (
        str(own["_id"]) if own else None,
        str(other["_id"]) if other else None
    )


# -----------------------------------------
# ADMIN REJECTS A COMPLAINT (invalid / fake, or a duplicate)
# -----------------------------------------

def reject_complaint(complaint_id, reason, note=""):

    object_id = to_object_id(complaint_id)

    if object_id is None or reason not in ("invalid", "duplicate"):
        return False

    complaint = get_db().complaints.find_one(
        {"_id": object_id, "status": {"$in": ["Submitted", "Verified"]}}
    )

    if complaint is None:
        return False

    rejected = _move_complaint(
        {"_id": object_id,
         "status": {"$in": ["Submitted", "Verified"]}},
        {"status": "Rejected",
         "rejected_reason": reason,
         "rejected_note": str(note).strip()[:300],
         "rejected_at": datetime.now()}
    )

    # A fake complaint is a strike for the citizen.
    # A duplicate is not the citizen's fault, so no strike.
    if rejected and reason == "invalid":
        log_violation(
            complaint["user_id"], "invalid_complaint", object_id,
            note or "Rejected as invalid"
        )

    return rejected


# -----------------------------------------
# WORKER PROOF PHOTO: has it been used before?
# -----------------------------------------

# True if this exact photo is already the citizen's report photo,
# or a proof photo for another job, or an old rejected proof photo.
def photo_already_used(photo_hash, complaint_id):

    return get_db().complaints.find_one({"$or": [
        {"image_hash": photo_hash},
        {"resolution_image_hash": photo_hash,
         "_id": {"$ne": to_object_id(complaint_id)}},
        {"old_proof_hashes": photo_hash}
    ]}) is not None


# -----------------------------------------
# CITIZEN REOPENS A RESOLVED COMPLAINT ("it is not fixed")
# -----------------------------------------
#
# Returns (True/False, message to show the citizen)

def reopen_complaint(complaint_id, user_id, reason):

    object_id = to_object_id(complaint_id)
    user_object_id = to_object_id(user_id)

    reason = str(reason).strip()[:300]

    if object_id is None or user_object_id is None:
        return False, "Complaint not found."

    if not reason:
        return False, "Please say what is still not fixed."

    complaint = get_db().complaints.find_one(
        {"_id": object_id, "user_id": user_object_id,
         "status": "Resolved"}
    )

    if complaint is None:
        return False, "Only your own resolved complaints can be reopened."

    if complaint.get("feedback_rating"):
        return False, "You already rated this complaint, so it cannot be reopened."

    if complaint.get("reopened"):
        return False, "This complaint was already reopened once."

    now = datetime.now()

    resolved_at = (
        complaint.get("resolved_at") or complaint.get("updated_at") or now
    )

    if now - resolved_at > timedelta(days=REOPEN_WINDOW_DAYS):
        return False, (
            f"A complaint can only be reopened within "
            f"{REOPEN_WINDOW_DAYS} days of being resolved."
        )

    if get_db().payments.find_one(
        {"complaint_id": object_id, "status": "paid"}
    ):
        return False, "The payment for this job was already paid, so it cannot be reopened."

    # The job goes back to the same worker with a fresh deadline
    reopened = _move_complaint(
        {"_id": object_id, "user_id": user_object_id,
         "status": "Resolved", "feedback_rating": None,
         "reopened": {"$ne": True}},
        {"status": "In Progress",
         "worker_done": False,
         "worker_done_at": None,
         "resolved_at": None,
         "was_late": False,
         "deadline": now + timedelta(days=REOPEN_DEADLINE_DAYS),
         "reopened": True,
         "work_rejected_reason": None,
         "reopened_at": now,
         "reopen_reason": reason,
         "previous_resolution_image": complaint.get(
             "resolution_image_filename"),
         "resolution_image_filename": None,
         "resolution_image_hash": None}
    )

    if not reopened:
        return False, "This complaint could not be reopened."

    # Remember the old proof photo so it cannot be uploaded again
    if complaint.get("resolution_image_hash"):
        get_db().complaints.update_one(
            {"_id": object_id},
            {"$push": {"old_proof_hashes": complaint["resolution_image_hash"]}}
        )

    # Hold the payment until the job is fixed and resolved again
    get_db().payments.update_many(
        {"complaint_id": object_id, "status": "pending"},
        {"$set": {"status": "on_hold"}}
    )

    # The reopen counts against the worker
    if complaint.get("assigned_worker_id"):
        log_violation(
            complaint["assigned_worker_id"], "reopened", object_id,
            reason
        )

    return True, "Complaint reopened. It has gone back to the worker."


# -----------------------------------------
# LOW-RATING PENALTY REVIEW (the admin has the final say)
# -----------------------------------------

def count_pending_reviews():

    return get_db().complaints.count_documents(
        {"rating_penalty": "pending"}
    )


# Complaints with a low rating that wait for the admin's decision
def get_rating_reviews():

    records = list(
        get_db().complaints.find(
            {"rating_penalty": "pending"}
        ).sort("feedback_at", 1)
    )

    ids = set()

    for record in records:
        ids.add(record["user_id"])

        if record.get("assigned_worker_id"):
            ids.add(record["assigned_worker_id"])

    users = {
        user["_id"]: user
        for user in get_db().users.find({"_id": {"$in": list(ids)}})
    }

    reviews = []

    for record in records:

        review = complaint_to_dict(record)

        citizen = users.get(record["user_id"], {})
        worker = users.get(record.get("assigned_worker_id"), {})

        review["citizen_name"] = citizen.get("name", "Unknown")
        review["worker_name"] = worker.get("name", "-")

        reviews.append(review)

    return reviews


# Returns (True/False, message for the admin)
def decide_rating_penalty(complaint_id, approve, note=""):

    object_id = to_object_id(complaint_id)

    if object_id is None:
        return False, "Complaint not found."

    complaint = get_db().complaints.find_one(
        {"_id": object_id, "rating_penalty": "pending"}
    )

    if complaint is None:
        return False, "This review was already decided."

    result = get_db().complaints.update_one(
        {"_id": object_id, "rating_penalty": "pending"},
        {"$set": {
            "rating_penalty": "approved" if approve else "dismissed",
            "rating_penalty_note": str(note).strip()[:300],
            "rating_penalty_decided_at": datetime.now()
        }}
    )

    if result.modified_count != 1:
        return False, "This review was already decided."

    if not approve:
        return True, "Penalty dismissed. The payment stays as it is."

    # Approved: it counts against the worker and reduces the payment
    if complaint.get("assigned_worker_id"):
        log_violation(
            complaint["assigned_worker_id"], "low_rating_penalty",
            object_id,
            f"Rating {complaint.get('feedback_rating')}/5 - "
            f"Rs. {RATING_PENALTY} penalty approved"
        )

    payment = get_db().payments.find_one({"complaint_id": object_id})

    if payment is None:
        return True, (
            f"Penalty approved. Rs. {RATING_PENALTY} will be deducted "
            "when the payment is created."
        )

    if payment["status"] == "paid":
        return True, (
            "Penalty approved, but the payment was already paid, so "
            "nothing could be deducted."
        )

    penalty = payment.get("penalty", 0) + RATING_PENALTY

    get_db().payments.update_one(
        {"_id": payment["_id"]},
        {"$set": {
            "penalty": penalty,
            "penalty_rating": RATING_PENALTY,
            "net_amount": max(round(payment["amount"] - penalty, 2), 0)
        }}
    )

    return True, f"Penalty approved. Rs. {RATING_PENALTY} deducted from the payment."
