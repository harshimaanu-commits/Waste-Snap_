
import hashlib
import os
from uuid import uuid4

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
    current_app
)

from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from db_helpers import (
    create_complaint,
    get_complaints_by_user,
    add_feedback,
    reopen_complaint,
    find_duplicates,
    count_reports_today,
    count_strikes,
    MAX_REPORTS_PER_DAY,
    STRIKE_LIMIT,
    STRIKE_DAYS,
    DUPLICATE_DAYS,
    REOPEN_WINDOW_DAYS
)


# Create Blueprint
complaints_bp = Blueprint("complaints", __name__)

# Complaint types shown in the report form
ISSUE_TYPES = [
    "Garbage accumulation",
    "Illegal dumping",
    "Overflowing bin",
    "Plastic waste",
    "Construction waste",
    "Pothole",
    "Other"
]

# Largest "days the problem has existed" a citizen can enter (10 years)
MAX_DAYS_EXISTING = 3650

# Allowed photograph formats
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


# -----------------------------------------
# REPORT A CIVIC ISSUE
# -----------------------------------------

@complaints_bp.route("/report", methods=["GET", "POST"])
@login_required
def report_issue():

    # Only citizens can submit complaints
    if current_user.role != "citizen":
        abort(403)

    # Display the reporting form
    if request.method == "GET":
        return render_template(
            "report_issue.html",
            issue_types=ISSUE_TYPES,
            reports_left=max(
                MAX_REPORTS_PER_DAY - count_reports_today(current_user.id),
                0
            ),
            max_reports=MAX_REPORTS_PER_DAY,
            strikes=count_strikes(current_user.id),
            strike_limit=STRIKE_LIMIT
        )

    # Read information from the form
    issue_type = request.form.get("type", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()
    days_text = request.form.get("days_existing", "").strip()
    image = request.files.get("image")

    # Validate required fields
    if issue_type not in ISSUE_TYPES:
        flash("Please select a valid issue type.", "danger")
        return redirect(url_for("complaints.report_issue"))

    if not description or not location:
        flash("Please fill in all fields.", "danger")
        return redirect(url_for("complaints.report_issue"))

    if len(description) > 2000:
        flash("Description is too long.", "danger")
        return redirect(url_for("complaints.report_issue"))

    if len(location) > 255:
        flash("Location is too long.", "danger")
        return redirect(url_for("complaints.report_issue"))

    # How many days the problem has already existed (0 to 3650)
    if not days_text.isdigit() or int(days_text) > MAX_DAYS_EXISTING:
        flash(
            "Please enter how many days the problem has existed "
            f"(0 to {MAX_DAYS_EXISTING}).",
            "danger"
        )
        return redirect(url_for("complaints.report_issue"))

    days_existing = int(days_text)

    # Make sure a photograph was uploaded
    if not image or not image.filename:
        flash("Please upload a photograph.", "danger")
        return redirect(url_for("complaints.report_issue"))

    # Check the uploaded file extension
    safe_name = secure_filename(image.filename)

    if "." not in safe_name:
        flash("Invalid image file.", "danger")
        return redirect(url_for("complaints.report_issue"))

    extension = safe_name.rsplit(".", 1)[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        flash("Only JPG, PNG and WEBP images are allowed.", "danger")
        return redirect(url_for("complaints.report_issue"))

    # ---- Citizen rules -------------------------------------------

    # 1. Too many invalid complaints: reporting is paused
    if count_strikes(current_user.id) >= STRIKE_LIMIT:
        flash(
            f"Reporting is paused: {STRIKE_LIMIT} of your complaints were "
            f"rejected as invalid in the last {STRIKE_DAYS} days. "
            "Strikes expire after that, or contact the admin.",
            "danger"
        )
        return redirect(url_for("dashboard", role="citizen"))

    # 2. Daily limit
    if count_reports_today(current_user.id) >= MAX_REPORTS_PER_DAY:
        flash(
            f"Daily limit reached: you can send at most "
            f"{MAX_REPORTS_PER_DAY} reports per day. Please try tomorrow.",
            "warning"
        )
        return redirect(url_for("complaints.my_complaints"))

    # 3. The same problem reported again
    own_duplicate, other_duplicate = find_duplicates(
        current_user.id, issue_type, location
    )

    if own_duplicate:
        flash(
            f"You already reported this problem (complaint "
            f"#{own_duplicate[-6:]}) in the last {DUPLICATE_DAYS} days "
            "and it is still open. It is shown below.",
            "warning"
        )
        return redirect(
            url_for("complaints.my_complaints")
            + "#c-" + own_duplicate
        )

    # Fingerprint of the photo, so a worker cannot re-use it as proof
    photo_hash = hashlib.sha256(image.read()).hexdigest()
    image.stream.seek(0)

    # Generate a unique filename to prevent duplicates
    filename = f"{uuid4().hex}.{extension}"

    # Save the photograph in static/uploads
    upload_folder = os.path.join(
        current_app.static_folder, "uploads"
    )

    os.makedirs(upload_folder, exist_ok=True)

    image.save(os.path.join(upload_folder, filename))

    # Save complaint details in MongoDB
    create_complaint(
        user_id=current_user.id,
        issue_type=issue_type,
        description=description,
        location=location,
        image_filename=filename,
        days_existing=days_existing,
        image_hash=photo_hash,
        possible_duplicate_of=other_duplicate
    )

    flash("Complaint submitted successfully!", "success")

    # Someone else reported the same thing: still saved, but flagged
    if other_duplicate:
        flash(
            "Someone has already reported a similar problem at this "
            "location. Yours was added too, and the admin can see both.",
            "warning"
        )

    return redirect(url_for("dashboard", role="citizen"))



# -----------------------------------------
# VIEW MY COMPLAINTS
# -----------------------------------------

@complaints_bp.route("/my-complaints")
@login_required
def my_complaints():

    # Only citizens can access this page
    if current_user.role != "citizen":
        abort(403)

    # Get complaints submitted by logged-in citizen
    complaints = get_complaints_by_user(current_user.id)

    # Send complaint data to the HTML page
    return render_template(
        "my_complaints.html",
        complaints=complaints,
        reopen_days=REOPEN_WINDOW_DAYS
    )



# -----------------------------------------
# GIVE A RATING AND FEEDBACK (after the complaint is resolved)
# -----------------------------------------

@complaints_bp.route(
    "/complaints/<complaint_id>/feedback",
    methods=["POST"]
)
@login_required
def give_feedback(complaint_id):

    # Only citizens can rate their own complaints
    if current_user.role != "citizen":
        abort(403)

    rating = request.form.get("rating", type=int)
    comment = request.form.get("comment", "")

    if add_feedback(complaint_id, current_user.id, rating, comment):
        flash("Thank you for your feedback!", "success")
    else:
        flash(
            "Could not save feedback. Choose a rating from 1 to 5. "
            "You can rate a resolved complaint only once.",
            "danger"
        )

    return redirect(url_for("complaints.my_complaints"))



# -----------------------------------------
# REOPEN A RESOLVED COMPLAINT ("it is not fixed")
# -----------------------------------------

@complaints_bp.route(
    "/complaints/<complaint_id>/reopen",
    methods=["POST"]
)
@login_required
def reopen(complaint_id):

    # Only citizens can reopen their own complaints
    if current_user.role != "citizen":
        abort(403)

    success, message = reopen_complaint(
        complaint_id,
        current_user.id,
        request.form.get("reason", "")
    )

    flash(message, "success" if success else "danger")

    return redirect(url_for("complaints.my_complaints"))
