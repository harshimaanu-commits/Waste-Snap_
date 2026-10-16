
from flask import (
    Blueprint,
    send_from_directory,
    render_template,
    abort,
    redirect,
    url_for,
    flash,
    request
)
from flask_login import login_required, current_user


from payment_gateway import start_payment
from data_export import (
    export_all,
    export_dir,
    list_files,
    downloadable_names,
    COLLECTIONS
)
from db_helpers import (
    get_all_complaints,
    verify_complaint,
    get_workers,
    assign_complaint,
    resolve_complaint,
    get_companies,
    get_resolved_without_payment,
    get_payments,
    create_payment,
    get_payment,
    approve_payment_request,
    reject_payment_request,
    reject_complaint,
    reject_work,
    get_rating_reviews,
    decide_rating_penalty,
    count_pending_reviews,
    get_violations,
    LATE_PENALTY,
    RATING_PENALTY,
    RESPONSE_WARNING_HOURS,
    REJECT_DEADLINE_DAYS
)



# Create the Admin Blueprint
admin_bp = Blueprint("admin", __name__)



# -----------------------------------------
# ADMIN DASHBOARD
# -----------------------------------------

@admin_bp.route("/admin")
@login_required
def dashboard():

    # Only admins can access this page
    if current_user.role != "admin":
        abort(403)

    # Retrieve all complaints
    complaints = get_all_complaints()

    # Retrieve available workers
    workers = get_workers()

    # Pass both lists to the HTML template
    return render_template(
        "admin_dashboard.html",
        complaints=complaints,
        workers=workers,
        pending_reviews=count_pending_reviews(),
        response_hours=RESPONSE_WARNING_HOURS
    )



# -----------------------------------------
# ADMIN - VERIFY COMPLAINT
# -----------------------------------------

@admin_bp.route(
    "/admin/verify/<complaint_id>",
    methods=["POST"]
)
@login_required
def verify(complaint_id):

    # Only administrators can verify complaints
    if current_user.role != "admin":
        abort(403)

    # Update the complaint using our database helper
    success = verify_complaint(complaint_id)

    if success:
        flash(
            "Complaint verified successfully!",
            "success"
        )
    else:
        flash(
            "Complaint not found or already processed.",
            "warning"
        )

    # Return to the Admin Dashboard
    return redirect(url_for("admin.dashboard"))



# -----------------------------------------
# ADMIN - ASSIGN COMPLAINT
# -----------------------------------------

@admin_bp.route(
    "/admin/assign/<complaint_id>",
    methods=["POST"]
)
@login_required
def assign(complaint_id):

    # Only admins can assign complaints
    if current_user.role != "admin":
        abort(403)

    # Read the selected worker's ID
    worker_id = request.form.get("worker_id")

    # Assign the complaint using our helper
    success = assign_complaint(
        complaint_id,
        worker_id
    )

    if success:
        flash(
            "Complaint assigned successfully!",
            "success"
        )
    else:
        flash(
            "Unable to assign complaint. Check its status and worker.",
            "danger"
        )

    # Return to Admin Dashboard
    return redirect(url_for("admin.dashboard"))



# -----------------------------------------
# ADMIN - RESOLVE COMPLAINT
# -----------------------------------------

@admin_bp.route(
    "/admin/resolve/<complaint_id>",
    methods=["POST"]
)
@login_required
def resolve(complaint_id):

    # Only admin users can resolve complaints
    if current_user.role != "admin":
        abort(403)

    # Update the complaint in MongoDB
    success = resolve_complaint(complaint_id)

    if success:
        flash(
            "Complaint resolved successfully!",
            "success"
        )
    else:
        flash(
            "Cannot resolve complaint. "
            "Worker completion and photo are required.",
            "danger"
        )

    # Return to the Admin Dashboard
    return redirect(url_for("admin.dashboard"))



# -----------------------------------------
# ADMIN - PAYMENTS PAGE
# -----------------------------------------

@admin_bp.route("/admin/payments")
@login_required
def payments():

    if current_user.role != "admin":
        abort(403)

    return render_template(
        "admin_payments.html",
        unpaid_complaints=get_resolved_without_payment(),
        companies=get_companies(),
        payments=get_payments(),
        late_penalty=LATE_PENALTY,
        rating_penalty=RATING_PENALTY
    )



# -----------------------------------------
# ADMIN - PAY A COMPANY FOR A RESOLVED COMPLAINT
# -----------------------------------------

@admin_bp.route(
    "/admin/payments/create/<complaint_id>",
    methods=["POST"]
)
@login_required
def create_company_payment(complaint_id):

    if current_user.role != "admin":
        abort(403)

    success = create_payment(
        complaint_id,
        request.form.get("company_id"),
        request.form.get("amount", "")
    )

    if success:
        flash("Payment created for the company.", "success")
    else:
        flash(
            "Could not create the payment. Choose a company "
            "and enter an amount above 0.",
            "danger"
        )

    return redirect(url_for("admin.payments"))



# -----------------------------------------
# ADMIN - APPROVE OR REJECT A COMPANY'S PAYMENT REQUEST
# -----------------------------------------

@admin_bp.route(
    "/admin/payments/<payment_id>/approve",
    methods=["POST"]
)
@login_required
def approve_request(payment_id):

    if current_user.role != "admin":
        abort(403)

    success, message = approve_payment_request(
        payment_id,
        request.form.get("amount")
    )

    flash(message, "success" if success else "danger")

    return redirect(url_for("admin.payments"))



@admin_bp.route(
    "/admin/payments/<payment_id>/reject",
    methods=["POST"]
)
@login_required
def reject_request(payment_id):

    if current_user.role != "admin":
        abort(403)

    success, message = reject_payment_request(
        payment_id,
        request.form.get("reason", "")
    )

    flash(message, "success" if success else "danger")

    return redirect(url_for("admin.payments"))



# -----------------------------------------
# ADMIN - PAY A COMPANY (the simulated checkout)
# -----------------------------------------

@admin_bp.route(
    "/admin/payments/<payment_id>/checkout",
    methods=["GET", "POST"]
)
@login_required
def checkout(payment_id):

    if current_user.role != "admin":
        abort(403)

    payment = get_payment(payment_id)

    if payment is None:
        abort(404)

    # Already being paid: show the live screen instead
    if payment["status"] == "processing":
        return redirect(url_for("payments.live", payment_id=payment_id))

    if payment["status"] not in ("pending", "failed"):
        flash(
            f"This payment cannot be paid now (it is {payment['status']}).",
            "warning"
        )
        return redirect(url_for("admin.payments"))

    if request.method == "POST":

        success, message = start_payment(
            payment_id,
            request.form.get("method", ""),
            request.form
        )

        if success:
            return redirect(url_for("payments.live", payment_id=payment_id))

        flash(message, "danger")

    # Suggested details for the payee (only to save typing in the demo)
    slug = "".join(
        ch for ch in payment["company_name"].lower() if ch.isalnum()
    ) or "company"

    return render_template(
        "payment_checkout.html",
        payment=payment,
        selected=request.form.get("method", "upi"),
        form=request.form,
        suggested_upi=f"{slug}@wastesnap",
        suggested_holder=payment["company_name"]
    )



# -----------------------------------------
# ADMIN - REJECT A COMPLAINT (invalid / fake, or duplicate)
# -----------------------------------------

@admin_bp.route(
    "/admin/reject/<complaint_id>",
    methods=["POST"]
)
@login_required
def reject(complaint_id):

    if current_user.role != "admin":
        abort(403)

    reason = request.form.get("reason", "")

    if reject_complaint(
        complaint_id, reason, request.form.get("note", "")
    ):
        if reason == "invalid":
            flash(
                "Complaint rejected as invalid. The citizen got a strike.",
                "success"
            )
        else:
            flash(
                "Complaint rejected as a duplicate. No strike was given.",
                "success"
            )
    else:
        flash(
            "Only new or verified complaints can be rejected.",
            "warning"
        )

    return redirect(url_for("admin.dashboard"))



# -----------------------------------------
# ADMIN - REJECT THE WORKER'S FINISHED WORK
# -----------------------------------------

@admin_bp.route(
    "/admin/reject-work/<complaint_id>",
    methods=["POST"]
)
@login_required
def reject_worker_work(complaint_id):

    if current_user.role != "admin":
        abort(403)

    success, message = reject_work(
        complaint_id,
        request.form.get("reason", "")
    )

    flash(message, "success" if success else "warning")

    return redirect(url_for("admin.dashboard"))



# -----------------------------------------
# ADMIN - REVIEWS (low ratings) AND VIOLATION LOG
# -----------------------------------------

@admin_bp.route("/admin/reviews")
@login_required
def reviews():

    if current_user.role != "admin":
        abort(403)

    return render_template(
        "admin_reviews.html",
        reviews=get_rating_reviews(),
        violations=get_violations(),
        rating_penalty=RATING_PENALTY
    )



# -----------------------------------------
# ADMIN - DECIDE A LOW-RATING PENALTY
# -----------------------------------------

@admin_bp.route(
    "/admin/reviews/<complaint_id>/decide",
    methods=["POST"]
)
@login_required
def decide_review(complaint_id):

    if current_user.role != "admin":
        abort(403)

    decision = request.form.get("decision")

    if decision not in ("approve", "dismiss"):
        flash("Please choose approve or dismiss.", "warning")
        return redirect(url_for("admin.reviews"))

    success, message = decide_rating_penalty(
        complaint_id,
        decision == "approve",
        request.form.get("note", "")
    )

    flash(message, "success" if success else "warning")

    return redirect(url_for("admin.reviews"))



# -----------------------------------------
# ADMIN - THE DATABASE COPY IN FILES
# -----------------------------------------

@admin_bp.route("/admin/data")
@login_required
def data_files():

    if current_user.role != "admin":
        abort(403)

    return render_template(
        "admin_data.html",
        files=list_files(),
        collections=COLLECTIONS
    )



@admin_bp.route("/admin/data/export", methods=["POST"])
@login_required
def export_now():

    if current_user.role != "admin":
        abort(403)

    result = export_all()

    if result["ok"]:
        counts = ", ".join(
            f"{count} {name}" for name, count in result["counts"].items()
        )
        message = f"Files updated ({counts})."

        if not result["db_file_updated"]:
            message += (
                " The .db file could not be replaced (is it open in "
                "another program?), so it still has the older data."
            )

        flash(message, "success" if result["db_file_updated"] else "warning")

    else:
        flash("Could not write the files: " + result["error"], "danger")

    return redirect(url_for("admin.data_files"))



@admin_bp.route("/admin/data/download/<path:name>")
@login_required
def download_data_file(name):

    if current_user.role != "admin":
        abort(403)

    # Only the known files can be downloaded
    if name not in downloadable_names():
        abort(404)

    return send_from_directory(export_dir(), name, as_attachment=True)
