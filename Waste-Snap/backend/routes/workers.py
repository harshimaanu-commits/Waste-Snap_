
import hashlib
import os
from uuid import uuid4

from flask import current_app, request
from werkzeug.utils import secure_filename

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    abort
)

from flask_login import login_required, current_user


from db_helpers import (
    get_worker_complaints,
    start_work_on_complaint,
    mark_work_done,
    worker_summary,
    photo_already_used,
    log_violation,
    DEADLINE_DAYS,
    LATE_PENALTY,
    RATING_PENALTY,
    START_WARNING_HOURS
)



# Create Worker Blueprint
workers_bp = Blueprint("workers", __name__)


# -----------------------------------------
# WORKER DASHBOARD
# -----------------------------------------

@workers_bp.route("/worker")
@login_required
def dashboard():

    # Only workers can access this page
    if current_user.role != "worker":
        abort(403)

    # Retrieve complaints assigned to this worker
    complaints = get_worker_complaints(current_user.id)

    # Send complaints to the HTML page
    return render_template(
        "worker_dashboard.html",
        complaints=complaints,
        summary=worker_summary(complaints),
        deadline_days=DEADLINE_DAYS,
        late_penalty=LATE_PENALTY,
        rating_penalty=RATING_PENALTY,
        start_hours=START_WARNING_HOURS
    )


# -----------------------------------------
# WORKER STARTS WORK
# -----------------------------------------

@workers_bp.route(
    "/worker/start/<complaint_id>",
    methods=["POST"]
)
@login_required
def start_work(complaint_id):

    # Only workers can update their tasks
    if current_user.role != "worker":
        abort(403)

    # Update complaint using the helper function
    success = start_work_on_complaint(
        complaint_id,
        current_user.id
    )

    if success:
        flash(
            "Complaint marked as In Progress!",
            "success"
        )
    else:
        flash(
            "Unable to update this complaint.",
            "danger"
        )

    # Return to Worker Dashboard
    return redirect(url_for("workers.dashboard"))


# -----------------------------------------
# WORKER UPLOADS PHOTO AND MARKS JOB DONE
# -----------------------------------------

@workers_bp.route(
    "/worker/done/<complaint_id>",
    methods=["POST"]
)
@login_required
def mark_done(complaint_id):

    # Only workers can complete jobs
    if current_user.role != "worker":
        abort(403)

    # Get the uploaded completion photograph
    image = request.files.get("fixed_image")

    # Photograph is mandatory
    if not image or not image.filename:
        flash("Please upload a photo of the fixed issue.", "danger")
        return redirect(url_for("workers.dashboard"))

    # Validate the filename and extension
    safe_name = secure_filename(image.filename)

    allowed_extensions = {"jpg", "jpeg", "png", "webp"}

    if "." not in safe_name:
        flash("Invalid image file.", "danger")
        return redirect(url_for("workers.dashboard"))

    extension = safe_name.rsplit(".", 1)[1].lower()

    if extension not in allowed_extensions:
        flash("Only JPG, PNG and WEBP images are allowed.", "danger")
        return redirect(url_for("workers.dashboard"))

    # The proof must be a NEW photo: not the citizen's photo,
    # and not a photo already used for another job
    photo_hash = hashlib.sha256(image.read()).hexdigest()
    image.stream.seek(0)

    if photo_already_used(photo_hash, complaint_id):
        log_violation(
            current_user.id, "duplicate_photo", complaint_id,
            "Tried to upload a photo that was already used"
        )
        flash(
            "This photo has already been used (as a report photo or as "
            "proof for a job). Please upload a new photo of the cleaned "
            "place. This attempt has been recorded.",
            "danger"
        )
        return redirect(url_for("workers.dashboard"))

    # Generate a unique filename
    filename = f"{uuid4().hex}.{extension}"

    # Store the photo in static/uploads
    upload_folder = os.path.join(
        current_app.static_folder, "uploads"
    )

    os.makedirs(upload_folder, exist_ok=True)

    file_path = os.path.join(upload_folder, filename)

    # Save the photo before marking work as done
    image.save(file_path)

    try:
        # Update complaint in MongoDB
        success = mark_work_done(
            complaint_id,
            current_user.id,
            filename,
            photo_hash
        )

    except Exception:
        # Remove the uploaded file if database saving fails
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    if success:
        flash(
            "Photo uploaded! Work marked as done.",
            "success"
        )
    else:
        # Avoid keeping unused photographs
        if os.path.exists(file_path):
            os.remove(file_path)

        flash(
            "Unable to complete this complaint.",
            "danger"
        )

    return redirect(url_for("workers.dashboard"))
